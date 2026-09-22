from __future__ import annotations

import hashlib
import math
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO, Final

import numpy as np
from numpy.typing import NDArray

from samplecore.models.morph import MORPH_WEIGHT_STEPS, HeardMorphPoint, MorphPair, MorphServiceStatus
from samplecore.models.sample_file import SampleFileLocation
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplecore.storage.sample_audio import SampleUnavailableError, read_sample_file, read_sample_file_frame_count
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.envelope.payload import response_payload
from samplemorph.envelope.response import ResponseReading, build_envelope_response
from samplemorph.heard import common_rate
from samplemorph.rendering import wav_bytes
from samplemorph.routes.envelope import PreparedPair
from samplemorph.routes.named import NamedRoute, select_route
from samplemorph.routes.route import HeardMono, hear_in_frame
from samplemorph.service.caches import LruCache
from samplemorph.service.settings import ServiceSettings
from samplemorph.service.uploads import UploadedSound, decode_upload

ETAG_LENGTH: Final[int] = 32
WARM_UP_FRAMES: Final[int] = 4096
WARM_UP_FREQUENCY_HZ: Final[float] = 440.0
WARM_UP_WEIGHT: Final[float] = 0.5

PairKey = tuple[str, str, float, float]
ResponseKey = MorphPair | tuple[str, str]


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

    Audio is rendered through the route the process serves and a filter is read under the route
    filters are built from, so a process whose renders glide hands over the filter between a pair all
    the same.
    """

    def __init__(self, *, settings: ServiceSettings, rendered: NamedRoute, filtered: NamedRoute) -> None:
        self._settings = settings
        self._rendered = rendered
        self._filtered = filtered
        self._fingerprint = rendered.fingerprint
        self._filter_fingerprint = filtered.fingerprint
        self._pairs: LruCache[PairKey, PreparedPair] = LruCache(
            capacity=settings.limits.pair_cache_bytes, weigh=lambda pair: pair.nbytes
        )
        self._renders: LruCache[HeardMorphPoint, bytes] = LruCache(
            capacity=settings.limits.render_cache_bytes, weigh=len
        )
        self._responses: LruCache[ResponseKey, bytes] = LruCache(
            capacity=settings.limits.response_cache_bytes, weigh=len
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

    @property
    def response_count(self) -> int:
        return len(self._responses)

    def check_bounds(self, pair: MorphPair) -> None:
        """Refuse a point whose render would reach past the process's limits, read from the stored headers alone.

        Raises:
            RenderBoundsError: the two rates lie further apart than the limits allow, or an end would
                render longer than the frame bound.
            FileNotFoundError: the store holds no object for an end read from the store.
            SampleUnavailableError: an end's file is gone, unreadable, or outside every sample directory served.
        """
        first_rate, second_rate = float(pair.first_rate_hz), float(pair.second_rate_hz)
        rate_hz = self._pair_rate(first_rate, second_rate)
        ends = ((pair.first, pair.first_file, first_rate), (pair.second, pair.second_file, second_rate))
        for sample_hash, sample_file, heard_rate in ends:
            self._check_frames(
                f"sample {sample_hash}",
                frame_count=self._frame_count(sample_hash, sample_file),
                heard_rate_hz=heard_rate,
                rate_hz=rate_hz,
            )

    def check_upload_bounds(self, first: UploadedSound, second: UploadedSound) -> None:
        """Refuse two uploaded sounds whose filter would be read past the process's limits.

        Raises:
            RenderBoundsError: the two rates lie further apart than the limits allow, or a sound would
                be read longer than the frame bound.
        """
        rate_hz = self._pair_rate(first.rate_hz, second.rate_hz)
        for named, sound in (("the first upload", first), ("the second upload", second)):
            self._check_frames(named, frame_count=sound.frame_count, heard_rate_hz=sound.rate_hz, rate_hz=rate_hz)

    def uploaded_sound(self, stream: IO[bytes]) -> UploadedSound:
        """The sound an uploaded file holds, read up to the bytes one request may carry.

        Raises:
            UploadTooLargeError: the upload runs past the byte bound.
            UploadUnreadableError: the bytes hold no audio this process decodes.
        """
        return decode_upload(stream, byte_limit=self._settings.limits.maximum_upload_bytes)

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

    def response(self, pair: MorphPair) -> bytes:
        """The bytes of the filter between two samples, which applies at every weight between them.

        A pair answers once and a listener moves the weight as often as they like, so the work is
        done per pair rather than per point and the bytes are kept the way a render is.

        Raises:
            FileNotFoundError: the store holds no object for an end read from the store.
            SampleUnavailableError: an end's file is gone, unreadable, holds another sample, or lies
                outside every sample directory served.
        """
        rate_hz = common_rate(float(pair.first_rate_hz), float(pair.second_rate_hz))
        return self._response_under(
            pair,
            rate_hz=rate_hz,
            ends=lambda: (
                self._heard(pair.first, pair.first_file, rate_hz=float(pair.first_rate_hz), target_rate_hz=rate_hz),
                self._heard(pair.second, pair.second_file, rate_hz=float(pair.second_rate_hz), target_rate_hz=rate_hz),
            ),
        )

    def uploaded_response(self, first: UploadedSound, second: UploadedSound) -> bytes:
        """The bytes of the filter between two sounds a caller sent, heard at the higher of their two rates.

        The sounds are named by what was sent, so a caller sending the same pair again is answered
        from memory.
        """
        rate_hz = common_rate(first.rate_hz, second.rate_hz)
        return self._response_under(
            (first.digest, second.digest),
            rate_hz=rate_hz,
            ends=lambda: (
                hear_in_frame(first.pcm, rate_hz=first.rate_hz, target_rate_hz=rate_hz),
                hear_in_frame(second.pcm, rate_hz=second.rate_hz, target_rate_hz=rate_hz),
            ),
        )

    def pair_etag(self, pair: MorphPair) -> str:
        """A validator naming this pair's filter under the route it is read through, for the caches between here and a caller."""
        named = "|".join(
            (self._filter_fingerprint, pair.first, pair.second, str(pair.first_rate_hz), str(pair.second_rate_hz))
        )
        return f'"{hashlib.sha256(named.encode()).hexdigest()[:ETAG_LENGTH]}"'

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
            name=self._rendered.name,
            fingerprint=self._fingerprint,
            weight_steps=MORPH_WEIGHT_STEPS,
            description=self._rendered.description,
        )

    def warm_up(self) -> None:
        """Render one synthetic tone against itself through the whole route, so the first request pays nothing extra.

        The phase integrator's compilation is paid on the first synthesis of a process; paying it
        here keeps it out of a listener's first click.
        """
        tone = HeardMono(mono=prepare_mono(_warm_up_tone()), rate_hz=NOMINAL_WAV_RATE)
        self._rendered.route.prepare_pair(tone, tone).render(weight=WARM_UP_WEIGHT)

    def _response_under(
        self, key: ResponseKey, *, rate_hz: float, ends: Callable[[], tuple[HeardMono, HeardMono]]
    ) -> bytes:
        """The response a key names: from memory when it was built before, from its two ends otherwise.

        The ends are read only once the response is known to be missing, and under the render lock,
        since reading them is the part of the work worth doing once.
        """
        cached = self._cached_response(key)
        if cached is not None:
            return cached

        with self._render_lock:
            cached = self._cached_response(key)
            if cached is not None:
                return cached

            route = self._filtered.route
            first, second = ends()
            reading = ResponseReading(
                geometry=route.geometry, settings=route.settings, envelope_settings=route.path.envelope_settings
            )
            response = build_envelope_response(
                route.analyze(first), route.analyze(second), rate_hz=rate_hz, reading=reading
            )
            written = response_payload(response)
            with self._cache_lock:
                self._responses.put(key, written)
            return written

    def _pair_rate(self, first_rate_hz: float, second_rate_hz: float) -> float:
        """The rate two sounds are heard at together, once their rates are known to lie within the limits.

        Raises:
            RenderBoundsError: the two rates lie further apart than the limits allow.
        """
        rate_hz = common_rate(first_rate_hz, second_rate_hz)
        ratio = rate_hz / min(first_rate_hz, second_rate_hz)
        if ratio > self._settings.limits.maximum_rate_ratio:
            raise RenderBoundsError(
                f"the two ends are heard {ratio:.1f} times apart in rate, and a morph spans at most "
                f"{self._settings.limits.maximum_rate_ratio:g}"
            )
        return rate_hz

    def _check_frames(self, named: str, *, frame_count: int, heard_rate_hz: float, rate_hz: float) -> None:
        """Refuse a sound that would be read past the frame bound once carried to the pair's rate.

        Raises:
            RenderBoundsError: the sound would be read longer than the frame bound.
        """
        maximum = self._settings.limits.maximum_frames
        frames = math.ceil(frame_count * rate_hz / heard_rate_hz)
        if frames > maximum:
            raise RenderBoundsError(
                f"{named} would render {frames} frames in this pair, past the {maximum} one morph renders"
            )

    def _cached_response(self, key: ResponseKey) -> bytes | None:
        with self._cache_lock:
            return self._responses.get(key)

    def _cached_render(self, point: HeardMorphPoint) -> bytes | None:
        with self._cache_lock:
            return self._renders.get(point)

    def _prepared(self, pair: MorphPair, *, rate_hz: float) -> PreparedPair:
        """Both ends of a point prepared by the route in the frame of `rate_hz`, remembered per pair of samples and rates."""
        key: PairKey = (pair.first, pair.second, float(pair.first_rate_hz), float(pair.second_rate_hz))
        with self._cache_lock:
            cached = self._pairs.get(key)
        if cached is not None:
            return cached

        prepared = self._rendered.route.prepare_pair(
            self._heard(pair.first, pair.first_file, rate_hz=float(pair.first_rate_hz), target_rate_hz=rate_hz),
            self._heard(pair.second, pair.second_file, rate_hz=float(pair.second_rate_hz), target_rate_hz=rate_hz),
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
    """Build the routes the settings select and warm the one that renders, so the renderer answers at speed from its first request."""
    renderer = MorphRenderer(
        settings=settings, rendered=select_route(settings.selection), filtered=select_route(settings.filter_selection)
    )
    renderer.warm_up()
    return renderer


def _warm_up_tone() -> NDArray[np.float64]:
    # (frames, 1): one channel, the shape every stored object's waveform has
    seconds = np.arange(WARM_UP_FRAMES, dtype=np.float64) / NOMINAL_WAV_RATE
    return np.sin(2.0 * np.pi * WARM_UP_FREQUENCY_HZ * seconds)[:, None]
