from __future__ import annotations

import hashlib
import math
import threading
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.models.morph import MORPH_WEIGHT_STEPS, HeardMorphPoint, MorphServiceStatus
from samplecore.models.sample_file import SampleFileLocation
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.sample_audio import SampleUnavailableError, read_sample_file, read_sample_file_frame_count
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.pipeline import common_rate
from samplemorph.rendering import wav_bytes
from samplemorph.routes.kinds import pair_through
from samplemorph.routes.named import NamedRoute, select_route
from samplemorph.routes.route import HeardMono, PreparedPair, hear_in_frame
from samplemorph.service.caches import LruCache
from samplemorph.service.settings import ServiceSettings

ETAG_LENGTH: Final[int] = 32
WARM_UP_FRAMES: Final[int] = 4096
WARM_UP_FREQUENCY_HZ: Final[float] = 440.0
WARM_UP_WEIGHT: Final[float] = 0.5

PairKey = tuple[str, str, float, float]


class RenderBoundsError(ValueError):
    """Raised when a point would render beyond what one process renders for a request."""


class MorphRenderer:
    """Renders any point between two stored samples through one route, remembering its work.

    A pair's two ends are prepared once, in the frame of the rate the pair is heard at, and kept
    per pair, so a slider over one pair prepares both ends once and then costs one render per
    weight; renders are cached per point, so a weight asked for twice is served from memory. Both
    caches are bounded by the bytes they hold. One lock serializes rendering, since a synthesis
    already spreads over every core and two at once would only contend; the caches have a lock of
    their own, so a render already made is served while another is being made.
    """

    def __init__(self, *, settings: ServiceSettings, named: NamedRoute) -> None:
        self._settings = settings
        self._named = named
        self._fingerprint = named.fingerprint
        self._pairs: LruCache[PairKey, PreparedPair] = LruCache(
            capacity=settings.limits.pair_cache_bytes, weigh=lambda pair: pair.nbytes
        )
        self._renders: LruCache[HeardMorphPoint, bytes] = LruCache(
            capacity=settings.limits.render_cache_bytes, weigh=len
        )
        self._cache_lock = threading.Lock()
        self._render_lock = threading.Lock()

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def pair_count(self) -> int:
        return len(self._pairs)

    @property
    def render_count(self) -> int:
        return len(self._renders)

    def check_bounds(self, point: HeardMorphPoint) -> None:
        """Refuse a point whose render would reach past the process's limits, read from the stored headers alone.

        Raises:
            RenderBoundsError: the two rates lie further apart than the limits allow, or an end would
                render longer than the frame bound.
            FileNotFoundError: the store holds no object for an end read from the store.
            SampleUnavailableError: an end's file is gone, unreadable, or outside every sample directory served.
        """
        limits = self._settings.limits
        first_rate, second_rate = float(point.first_rate_hz), float(point.second_rate_hz)
        rate_hz = common_rate(first_rate, second_rate)
        ratio = rate_hz / min(first_rate, second_rate)
        if ratio > limits.maximum_rate_ratio:
            raise RenderBoundsError(
                f"the two ends are heard {ratio:.1f} times apart in rate, and a morph spans at most "
                f"{limits.maximum_rate_ratio:g}"
            )
        ends = ((point.first, point.first_file, first_rate), (point.second, point.second_file, second_rate))
        for sample_hash, sample_file, heard_rate in ends:
            frames = math.ceil(self._frame_count(sample_hash, sample_file) * rate_hz / heard_rate)
            if frames > limits.maximum_frames:
                raise RenderBoundsError(
                    f"sample {sample_hash} would render {frames} frames in this pair, past the {limits.maximum_frames} "
                    "one morph renders"
                )

    def render(self, point: HeardMorphPoint) -> bytes:
        """The WAV bytes of one point, stating the rate the pair is heard at.

        Two identical requests arriving together render once: the second finds the first's render
        waiting once the render lock frees.

        Raises:
            FileNotFoundError: the store holds no object for an end read from the store.
            SampleUnavailableError: an end's file is gone, unreadable, holds another sample, or lies
                outside every sample directory served.
        """
        cached = self._cached_render(point)
        if cached is not None:
            return cached

        with self._render_lock:
            cached = self._cached_render(point)
            if cached is not None:
                return cached

            rate_hz = common_rate(float(point.first_rate_hz), float(point.second_rate_hz))
            waveform = self._prepared(point, rate_hz=rate_hz).render(weight=point.weight)
            rendered = wav_bytes(waveform, rate_hz=rate_hz)
            with self._cache_lock:
                self._renders.put(point, rendered)
            return rendered

    def etag(self, point: HeardMorphPoint) -> str:
        """A validator that names this point's render under the served route, for the caches between here and a listener."""
        named = "|".join(
            (
                self._fingerprint,
                point.first,
                point.second,
                str(point.step),
                str(point.first_rate_hz),
                str(point.second_rate_hz),
            )
        )
        return f'"{hashlib.sha256(named.encode()).hexdigest()[:ETAG_LENGTH]}"'

    def status(self) -> MorphServiceStatus:
        """What this renderer serves, for a caller deciding whether and how to ask."""
        return MorphServiceStatus(
            route=self._named.kind.value,
            name=self._named.name,
            device=self._named.device,
            fingerprint=self._fingerprint,
            weight_steps=MORPH_WEIGHT_STEPS,
            description=self._named.description,
        )

    def warm_up(self) -> None:
        """Render one synthetic tone against itself through the whole route, so the first request pays nothing extra.

        The phase integrator's compilation, and on the latent route the band matrix's pseudo-inverse,
        are paid on the first synthesis of a process; paying them here keeps them out of a
        listener's first click.
        """
        tone = HeardMono(mono=prepare_mono(_warm_up_tone()), rate_hz=NOMINAL_WAV_RATE)
        pair_through(self._named.route, tone, tone).render(weight=WARM_UP_WEIGHT)

    def _cached_render(self, point: HeardMorphPoint) -> bytes | None:
        with self._cache_lock:
            return self._renders.get(point)

    def _prepared(self, point: HeardMorphPoint, *, rate_hz: float) -> PreparedPair:
        """Both ends of a point prepared by the route in the frame of `rate_hz`, remembered per pair of samples and rates."""
        key: PairKey = (point.first, point.second, float(point.first_rate_hz), float(point.second_rate_hz))
        with self._cache_lock:
            cached = self._pairs.get(key)
        if cached is not None:
            return cached

        prepared = pair_through(
            self._named.route,
            self._heard(point.first, point.first_file, rate_hz=float(point.first_rate_hz), target_rate_hz=rate_hz),
            self._heard(point.second, point.second_file, rate_hz=float(point.second_rate_hz), target_rate_hz=rate_hz),
        )
        with self._cache_lock:
            self._pairs.put(key, prepared)
        return prepared

    def _heard(self, sample_hash: str, sample_file: Path | None, *, rate_hz: float, target_rate_hz: float) -> HeardMono:
        """An end as it sounds in the pair's frame: its frames heard at `rate_hz`, carried to `target_rate_hz`."""
        return hear_in_frame(self._read(sample_hash, sample_file).pcm, rate_hz=rate_hz, target_rate_hz=target_rate_hz)

    def _read(self, sample_hash: str, sample_file: Path | None) -> SamplePCM:
        """An end's waveform: its stored object by hash, or the file the request names for it."""
        if sample_file is None:
            return audio_store.read_object(self._settings.library_root, sample_hash)
        return read_sample_file(self._served_location(sample_file), sample_hash)

    def _frame_count(self, sample_hash: str, sample_file: Path | None) -> int:
        """How many frames an end holds, from the stored object's header or the named file's."""
        if sample_file is None:
            return audio_store.stored_frame_count(self._settings.library_root, sample_hash)
        return read_sample_file_frame_count(self._served_location(sample_file))

    def _served_location(self, sample_file: Path) -> SampleFileLocation:
        """The named file as a location inside one of the sample directories this process serves.

        Raises:
            SampleUnavailableError: the file lies inside none of them.
        """
        location = SampleFileLocation.inside(sample_file, self._settings.sample_directories)
        if location is None:
            raise SampleUnavailableError(f"{sample_file} lies in no sample directory this process reads")
        return location


def load_renderer(settings: ServiceSettings) -> MorphRenderer:
    """Build the route the settings select and warm it, so the renderer answers at speed from its first request.

    Raises:
        FileNotFoundError: the latent route's model, or the restorer its vocoder reads, is stored under no such name.
        ModelFileChanged: a model file was written while the latent route was loaded from it.
    """
    renderer = MorphRenderer(settings=settings, named=select_route(settings.library_root, settings.selection))
    renderer.warm_up()
    return renderer


def _warm_up_tone() -> NDArray[np.float64]:
    # (frames, 1): one channel, the shape every stored object's waveform has
    seconds = np.arange(WARM_UP_FRAMES, dtype=np.float64) / NOMINAL_WAV_RATE
    return np.sin(2.0 * np.pi * WARM_UP_FREQUENCY_HZ * seconds)[:, None]
