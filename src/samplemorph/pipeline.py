from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.naming import choose_dominant_rate
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.codecs import SampleCodec
from samplemorph.images import SampleLatent
from samplemorph.morphers import Morpher, MorphWeights
from samplemorph.rendering import RenderedFile, RenderKind, rate_between, write_rendering
from samplemorph.vocoders import Vocoder

DEFAULT_MORPH_WEIGHTS: Final[tuple[float, ...]] = (0.25, 0.5, 0.75)


@dataclass(frozen=True)
class EncodedSample:
    """One catalog sample carried into the latent space, with what it takes to hear it again."""

    sample: Sample
    latent: SampleLatent
    mono: NDArray[np.float64]
    rate_hz: float


@dataclass(frozen=True)
class MorphRenderSummary:
    """What one render pass wrote, across every file it produced."""

    first_hash: str
    second_hash: str
    files: tuple[RenderedFile, ...]

    @property
    def morph_count(self) -> int:
        return sum(1 for file in self.files if file.kind is RenderKind.MORPH)


def encode_sample(
    connection: Connection,
    library_root: Path,
    sample: Sample,
    *,
    canonicalizer: Canonicalizer,
    codec: SampleCodec,
) -> EncodedSample:
    """Read one cataloged sample, canonicalize it, and encode it into the latent space.

    The playback rate travels alongside because the stored file states a nominal rate rather than a
    measured one, and every rendered file has to state the rate its content is heard at.

    Raises:
        ValueError: the catalog holds no occurrence of this sample, so no playback rate is known.
    """
    mono = audio_store.read(library_root, sample).pcm.mean(axis=1)
    rates_by_hash = PostgresSampleRepository(connection).names_and_rates_by_hash([sample.hash])[1]
    dominant_rate = choose_dominant_rate(rates_by_hash.get(sample.hash, ()))
    if dominant_rate is None:
        raise ValueError(f"sample {sample.hash} has no cataloged occurrence, so its playback rate is unknown")

    image = canonicalizer.canonicalize(mono)
    return EncodedSample(sample=sample, latent=codec.encode(image), mono=mono, rate_hz=float(dominant_rate))


def render_listening_set(
    first: EncodedSample,
    second: EncodedSample,
    *,
    canonicalizer: Canonicalizer,
    codec: SampleCodec,
    morpher: Morpher,
    vocoder: Vocoder,
    output_directory: Path,
    weights: tuple[float, ...] = DEFAULT_MORPH_WEIGHTS,
) -> MorphRenderSummary:
    """Write both originals, both reconstructions, and one file per morph weight.

    The originals are written beside the reconstructions on purpose: without hearing the untouched
    audio at the same playback rate, a listener cannot tell a codec that lost something from a
    sample that always sounded that way.
    """
    files = [
        write_rendering(
            output_directory / "original_first.wav",
            first.mono,
            rate_hz=first.rate_hz,
            kind=RenderKind.ORIGINAL,
            weight=0.0,
        ),
        _render_decoded(
            output_directory / "reconstruction_first.wav",
            first.latent,
            canonicalizer=canonicalizer,
            codec=codec,
            vocoder=vocoder,
            rate_hz=first.rate_hz,
            kind=RenderKind.RECONSTRUCTION,
            weight=0.0,
        ),
    ]
    for weight in weights:
        files.append(
            _render_decoded(
                output_directory / f"morph_{int(round(weight * 100)):03d}.wav",
                morpher.morph(first.latent, second.latent, weights=MorphWeights.uniform(weight)),
                canonicalizer=canonicalizer,
                codec=codec,
                vocoder=vocoder,
                rate_hz=rate_between(first.rate_hz, second.rate_hz, weight),
                kind=RenderKind.MORPH,
                weight=weight,
            )
        )
    files.extend(
        [
            _render_decoded(
                output_directory / "reconstruction_second.wav",
                second.latent,
                canonicalizer=canonicalizer,
                codec=codec,
                vocoder=vocoder,
                rate_hz=second.rate_hz,
                kind=RenderKind.RECONSTRUCTION,
                weight=1.0,
            ),
            write_rendering(
                output_directory / "original_second.wav",
                second.mono,
                rate_hz=second.rate_hz,
                kind=RenderKind.ORIGINAL,
                weight=1.0,
            ),
        ]
    )
    return MorphRenderSummary(first_hash=first.sample.hash, second_hash=second.sample.hash, files=tuple(files))


def decode_to_audio(
    latent: SampleLatent, *, canonicalizer: Canonicalizer, codec: SampleCodec, vocoder: Vocoder
) -> NDArray[np.float64]:
    """Carry a latent back to frames: decode it to an image, restore it, and estimate its phase."""
    return vocoder.synthesize(canonicalizer.restore(codec.decode(latent)))


def _render_decoded(
    path: Path,
    latent: SampleLatent,
    *,
    canonicalizer: Canonicalizer,
    codec: SampleCodec,
    vocoder: Vocoder,
    rate_hz: float,
    kind: RenderKind,
    weight: float | None,
) -> RenderedFile:
    waveform = decode_to_audio(latent, canonicalizer=canonicalizer, codec=codec, vocoder=vocoder)
    return write_rendering(path, waveform, rate_hz=rate_hz, kind=kind, weight=weight)
