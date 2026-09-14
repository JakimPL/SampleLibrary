from __future__ import annotations

import hashlib
import math
import threading
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.models.morph import MORPH_WEIGHT_STEPS, HeardMorphPoint, MorphServiceStatus
from samplecore.storage import audio_store
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.codecs.conditioned import ConditionedCodec
from samplemorph.images import SampleLatent
from samplemorph.pipeline import LoadedRoute, common_rate, encode_heard, encode_waveform, load_route, render_morph
from samplemorph.rendering import wav_bytes
from samplemorph.service.caches import LruCache
from samplemorph.service.settings import PROCESSOR_DEVICE, ServiceSettings
from samplemorph.vocoders.restored import RestoredPghiVocoder

ETAG_LENGTH: Final[int] = 32
WARM_UP_FRAMES: Final[int] = 4096
WARM_UP_FREQUENCY_HZ: Final[float] = 440.0
WARM_UP_WEIGHT: Final[float] = 0.5

LatentKey = tuple[str, float, float]


class RenderBoundsError(ValueError):
    """Raised when a point would render beyond what one process renders for a request."""


class MorphRenderer:
    """Renders any point between two stored samples through one loaded route, remembering its work.

    Latents are cached per sample and per frame it is carried into, so a slider over one pair
    encodes each endpoint once and then costs one decode and one synthesis per weight; renders are
    cached per point, so a weight asked for twice is served from memory. Both caches are bounded by
    the bytes they hold. One lock serializes rendering, since torch on the processor already spreads
    one synthesis over every core and two at once would only contend; the caches have a lock of
    their own, so a render already made is served while another is being made.
    """

    def __init__(self, *, settings: ServiceSettings, loaded: LoadedRoute) -> None:
        self._settings = settings
        self._loaded = loaded
        self._fingerprint = loaded.fingerprint
        self._latents: LruCache[LatentKey, SampleLatent] = LruCache(
            capacity=settings.limits.latent_cache_bytes, weigh=lambda latent: latent.values.nbytes
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
    def latent_count(self) -> int:
        return len(self._latents)

    @property
    def render_count(self) -> int:
        return len(self._renders)

    def check_bounds(self, point: HeardMorphPoint) -> None:
        """Refuse a point whose render would reach past the process's limits, read from the stored headers alone.

        Raises:
            RenderBoundsError: the two rates lie further apart than the limits allow, or an end would
                render longer than the frame bound.
            FileNotFoundError: the store holds no object for one of the two samples.
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
        for sample_hash, heard_rate in ((point.first, first_rate), (point.second, second_rate)):
            frames = math.ceil(
                audio_store.stored_frame_count(self._settings.library_root, sample_hash) * rate_hz / heard_rate
            )
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
            FileNotFoundError: the store holds no object for one of the two samples.
        """
        cached = self._cached_render(point)
        if cached is not None:
            return cached

        with self._render_lock:
            cached = self._cached_render(point)
            if cached is not None:
                return cached

            rate_hz = common_rate(float(point.first_rate_hz), float(point.second_rate_hz))
            waveform = render_morph(
                self._latent(point.first, rate_hz=float(point.first_rate_hz), target_rate_hz=rate_hz),
                self._latent(point.second, rate_hz=float(point.second_rate_hz), target_rate_hz=rate_hz),
                weight=point.weight,
                route=self._loaded.route,
            )
            rendered = wav_bytes(waveform, rate_hz=rate_hz)
            with self._cache_lock:
                self._renders.put(point, rendered)
            return rendered

    def etag(self, point: HeardMorphPoint) -> str:
        """A validator that names this point's render under the loaded route, for the caches between here and a listener."""
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
        choice = self._loaded.choice
        description = self._loaded.model.description
        restorer: str | None
        match self._loaded.route.vocoder:
            case RestoredPghiVocoder():
                restorer = choice.restorer_name
            case _:
                restorer = None
        return MorphServiceStatus(
            model=choice.model_name,
            codec=description.codec,
            canonicalizer=description.canonicalizer,
            latent_size=description.latent_size,
            vocoder=choice.vocoder_name,
            restorer=restorer,
            device=self._device(),
            fingerprint=self._fingerprint,
            weight_steps=MORPH_WEIGHT_STEPS,
        )

    def warm_up(self) -> None:
        """Render one synthetic tone through the whole route, so the first request pays nothing extra.

        The band matrix's pseudo-inverse and the phase integrator's compilation are paid on the
        first synthesis of a process; paying them here keeps them out of a listener's first click.
        """
        route = self._loaded.route
        encoded = encode_waveform(_warm_up_tone(), canonicalizer=route.canonicalizer, codec=route.codec)
        render_morph(encoded.latent, encoded.latent, weight=WARM_UP_WEIGHT, route=route)

    def _device(self) -> str:
        """The device the loaded networks run on, or the processor for a route that loads none."""
        match self._loaded.route.vocoder:
            case RestoredPghiVocoder(device=device):
                return str(device)
        match self._loaded.route.codec:
            case ConditionedCodec(device=device):
                return str(device)
        return PROCESSOR_DEVICE

    def _cached_render(self, point: HeardMorphPoint) -> bytes | None:
        with self._cache_lock:
            return self._renders.get(point)

    def _latent(self, sample_hash: str, *, rate_hz: float, target_rate_hz: float) -> SampleLatent:
        key: LatentKey = (sample_hash, rate_hz, target_rate_hz)
        with self._cache_lock:
            cached = self._latents.get(key)
        if cached is not None:
            return cached

        pcm = audio_store.read_object(self._settings.library_root, sample_hash).pcm
        route = self._loaded.route
        encoded = encode_heard(
            pcm, rate_hz=rate_hz, target_rate_hz=target_rate_hz, canonicalizer=route.canonicalizer, codec=route.codec
        )
        with self._cache_lock:
            self._latents.put(key, encoded.latent)
        return encoded.latent


def load_renderer(settings: ServiceSettings) -> MorphRenderer:
    """Load the route the settings name and warm it, so the renderer answers at speed from its first request.

    Raises:
        FileNotFoundError: the model, or the restorer the vocoder reads, is stored under no such name.
        ModelFileChanged: a model file was written while the route was loaded from it.
    """
    renderer = MorphRenderer(settings=settings, loaded=load_route(settings.library_root, settings.choice))
    renderer.warm_up()
    return renderer


def _warm_up_tone() -> NDArray[np.float64]:
    # (frames, 1): one channel, the shape every stored object's waveform has
    seconds = np.arange(WARM_UP_FRAMES, dtype=np.float64) / NOMINAL_WAV_RATE
    return np.sin(2.0 * np.pi * WARM_UP_FREQUENCY_HZ * seconds)[:, None]
