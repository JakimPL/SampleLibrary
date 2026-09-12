from __future__ import annotations

import hashlib
import threading
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.models.morph import MORPH_WEIGHT_STEPS, MorphPoint, MorphServiceStatus
from samplecore.storage import audio_store
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.images import SampleLatent
from samplemorph.model_store import MorphModel
from samplemorph.pipeline import MorphRoute, encode_waveform, load_route, render_morph
from samplemorph.rendering import wav_bytes
from samplemorph.service.caches import LruCache
from samplemorph.service.settings import LATENT_CACHE_SIZE, RENDER_CACHE_SIZE, ServiceSettings
from samplemorph.vocoders.restored import RestoredPghiVocoder

ETAG_LENGTH: Final[int] = 32
WARM_UP_FRAMES: Final[int] = 4096
WARM_UP_FREQUENCY_HZ: Final[float] = 440.0
WARM_UP_WEIGHT: Final[float] = 0.5


class MorphRenderer:
    """Renders any point between two stored samples through one loaded route, remembering its work.

    Latents are cached per sample, so a slider over one pair encodes each endpoint once and then
    costs one decode and one synthesis per weight; renders are cached per point, so a weight asked
    for twice is served from memory. One lock serializes rendering, since torch on the processor
    already spreads one synthesis over every core and two at once would only contend.
    """

    def __init__(self, *, settings: ServiceSettings, model: MorphModel, route: MorphRoute) -> None:
        self._settings = settings
        self._model = model
        self._route = route
        self._fingerprint = _fingerprint(model, route)
        self._latents: LruCache[str, SampleLatent] = LruCache(capacity=LATENT_CACHE_SIZE)
        self._renders: LruCache[MorphPoint, bytes] = LruCache(capacity=RENDER_CACHE_SIZE)
        self._lock = threading.Lock()

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def latent_count(self) -> int:
        return len(self._latents)

    @property
    def render_count(self) -> int:
        return len(self._renders)

    def render(self, point: MorphPoint) -> bytes:
        """The WAV bytes of one point, at the nominal header rate every stored object carries.

        Raises:
            FileNotFoundError: the store holds no object for one of the two samples.
        """
        with self._lock:
            cached = self._renders.get(point)
            if cached is not None:
                return cached

            waveform = render_morph(
                self._latent(point.first), self._latent(point.second), weight=point.weight, route=self._route
            )
            rendered = wav_bytes(waveform, rate_hz=NOMINAL_WAV_RATE)
            self._renders.put(point, rendered)
            return rendered

    def etag(self, point: MorphPoint) -> str:
        """A validator that names this point's render under the loaded model, for the caches between here and a listener."""
        digest = hashlib.sha256(f"{self._fingerprint}|{point.first}|{point.second}|{point.weight}".encode()).hexdigest()
        return f'"{digest[:ETAG_LENGTH]}"'

    def status(self) -> MorphServiceStatus:
        """What this renderer serves, for a caller deciding whether and how to ask."""
        restorer: str | None
        match self._route.vocoder:
            case RestoredPghiVocoder():
                restorer = self._settings.choice.restorer_name
            case _:
                restorer = None
        return MorphServiceStatus(
            model=self._settings.choice.model_name,
            codec=self._model.description.codec,
            canonicalizer=self._model.description.canonicalizer,
            latent_size=self._model.description.latent_size,
            vocoder=self._settings.choice.vocoder_name,
            restorer=restorer,
            device=self._settings.choice.device,
            fingerprint=self._fingerprint,
            weight_steps=MORPH_WEIGHT_STEPS,
        )

    def warm_up(self) -> None:
        """Render one synthetic tone through the whole route, so the first request pays nothing extra.

        The band matrix's pseudo-inverse and the phase integrator's compilation are paid on the
        first synthesis of a process; paying them here keeps them out of a listener's first click.
        """
        encoded = encode_waveform(_warm_up_tone(), canonicalizer=self._route.canonicalizer, codec=self._route.codec)
        render_morph(encoded.latent, encoded.latent, weight=WARM_UP_WEIGHT, route=self._route)

    def _latent(self, sample_hash: str) -> SampleLatent:
        cached = self._latents.get(sample_hash)
        if cached is not None:
            return cached

        pcm = audio_store.read_object(self._settings.library_root, sample_hash).pcm
        encoded = encode_waveform(pcm, canonicalizer=self._route.canonicalizer, codec=self._route.codec)
        self._latents.put(sample_hash, encoded.latent)
        return encoded.latent


def load_renderer(settings: ServiceSettings) -> MorphRenderer:
    """Load the route the settings name and warm it, so the renderer answers at speed from its first request.

    Raises:
        FileNotFoundError: the model, or the restorer the vocoder reads, is stored under no such name.
    """
    model, route = load_route(settings.library_root, settings.choice)
    renderer = MorphRenderer(settings=settings, model=model, route=route)
    renderer.warm_up()
    return renderer


def _fingerprint(model: MorphModel, route: MorphRoute) -> str:
    """One digest over the descriptions of every model file the route renders through."""
    parts = [model.description.model_dump_json()]
    match route.vocoder:
        case RestoredPghiVocoder(description=description):
            parts.append(description.model_dump_json())
        case _:
            parts.append(type(route.vocoder).__name__)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _warm_up_tone() -> NDArray[np.float64]:
    # (frames, 1): one channel, the shape every stored object's waveform has
    seconds = np.arange(WARM_UP_FRAMES, dtype=np.float64) / NOMINAL_WAV_RATE
    return np.sin(2.0 * np.pi * WARM_UP_FREQUENCY_HZ * seconds)[:, None]
