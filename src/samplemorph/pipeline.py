from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.models.sample import Sample
from samplecore.storage import audio_store
from samplecore.storage.playback_rates import resolved_playback_rates
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.codecs import SampleCodec
from samplemorph.images import SampleLatent
from samplemorph.model_store import MorphModel, MorphModelDescription, load_named_model
from samplemorph.morphers import Morpher, MorphWeights
from samplemorph.registries import MORPHER_REGISTRY, canonicalizer_for_geometry
from samplemorph.rendering import RenderedFile, RenderKind, rate_between, write_rendering
from samplemorph.vocoders import Vocoder
from samplemorph.vocoders.selection import vocoder_named

DEFAULT_MORPH_WEIGHTS: Final[tuple[float, ...]] = (0.25, 0.5, 0.75)
FIRST_ENDPOINT_WEIGHT: Final[float] = 0.0
SECOND_ENDPOINT_WEIGHT: Final[float] = 1.0


@dataclass(frozen=True)
class EncodedWaveform:
    """A waveform carried into the latent space, beside the mono it was read from."""

    mono: NDArray[np.float64]
    latent: SampleLatent


@dataclass(frozen=True)
class EncodedSample:
    """One catalog sample carried into the latent space, with what it takes to hear it again."""

    sample: Sample
    latent: SampleLatent
    mono: NDArray[np.float64]
    rate_hz: float


@dataclass(frozen=True)
class MorphRoute:
    """The route a sample takes from a latent back to audio, and the morpher that lands between two.

    A listening set is only readable when every file on it took the same route, so the four pieces
    that decide what is heard travel together and one set names one of these.
    """

    canonicalizer: Canonicalizer
    codec: SampleCodec
    vocoder: Vocoder
    morpher: Morpher


@dataclass(frozen=True)
class RouteChoice:
    """The names that pick a route: the stored model, the vocoder and the restorer it may read, the morpher, and the device."""

    model_name: str
    vocoder_name: str
    restorer_name: str
    morpher_name: str
    device: str


@dataclass(frozen=True)
class MorphRenderSummary:
    """What one render pass wrote, across every file it produced."""

    first_hash: str
    second_hash: str
    files: tuple[RenderedFile, ...]

    @property
    def morph_count(self) -> int:
        return sum(1 for file in self.files if file.kind is RenderKind.MORPH)


def load_route(library_root: Path, choice: RouteChoice) -> tuple[MorphModel, MorphRoute]:
    """Load the stored model a choice names and assemble the route that renders through it.

    The canonicalizer is the one the model's own geometry names, so a route always reads the axis
    its codec was fitted on.

    Raises:
        FileNotFoundError: the model, or the restorer the vocoder reads, is stored under no such name.
    """
    model = load_named_model(library_root, name=choice.model_name, device=choice.device)
    route = MorphRoute(
        canonicalizer=canonicalizer_for_geometry(model.description.geometry),
        codec=model.codec,
        vocoder=vocoder_named(
            choice.vocoder_name, library_root=library_root, restorer_name=choice.restorer_name, device=choice.device
        ),
        morpher=MORPHER_REGISTRY[choice.morpher_name](),
    )
    return model, route


def encode_waveform(pcm: NDArray[np.float64], *, canonicalizer: Canonicalizer, codec: SampleCodec) -> EncodedWaveform:
    """Fold a stored waveform to mono, canonicalize it, and encode it, with no catalog in reach."""
    mono = prepare_mono(pcm)
    return EncodedWaveform(mono=mono, latent=codec.encode(canonicalizer.canonicalize(mono)))


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
    measured one, and every rendered file has to state the rate its content is heard at. It is the
    rate the application plays the sample at: what the note events say first, the occurrences'
    dominant rate after.

    Raises:
        ValueError: the catalog holds no occurrence of this sample, so no playback rate is known.
    """
    encoded = encode_waveform(audio_store.read(library_root, sample).pcm, canonicalizer=canonicalizer, codec=codec)
    rate = resolved_playback_rates(connection, [sample.hash])[sample.hash]
    if rate is None:
        raise ValueError(f"sample {sample.hash} has no cataloged occurrence, so its playback rate is unknown")

    return EncodedSample(sample=sample, latent=encoded.latent, mono=encoded.mono, rate_hz=float(rate))


def render_morph(first: SampleLatent, second: SampleLatent, *, weight: float, route: MorphRoute) -> NDArray[np.float64]:
    """The audio at one weight between two latents: morph, decode, restore, and estimate the phase.

    At weight 0 or 1 the morpher returns an endpoint's own latent, so the same call renders a
    sample's reconstruction and every point between two.
    """
    return decode_to_audio(route.morpher.morph(first, second, weights=MorphWeights.uniform(weight)), route=route)


def render_listening_set(
    first: EncodedSample,
    second: EncodedSample,
    *,
    route: MorphRoute,
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
            RenderedFile(
                path=output_directory / "original_first.wav",
                kind=RenderKind.ORIGINAL,
                rate_hz=first.rate_hz,
                weight=FIRST_ENDPOINT_WEIGHT,
            ),
            first.mono,
        ),
        write_rendering(
            RenderedFile(
                path=output_directory / "reconstruction_first.wav",
                kind=RenderKind.RECONSTRUCTION,
                rate_hz=first.rate_hz,
                weight=FIRST_ENDPOINT_WEIGHT,
            ),
            render_morph(first.latent, second.latent, weight=FIRST_ENDPOINT_WEIGHT, route=route),
        ),
    ]
    for weight in weights:
        files.append(
            write_rendering(
                RenderedFile(
                    path=output_directory / f"morph_{int(round(weight * 100)):03d}.wav",
                    kind=RenderKind.MORPH,
                    rate_hz=rate_between(first.rate_hz, second.rate_hz, weight),
                    weight=weight,
                ),
                render_morph(first.latent, second.latent, weight=weight, route=route),
            )
        )
    files.extend(
        [
            write_rendering(
                RenderedFile(
                    path=output_directory / "reconstruction_second.wav",
                    kind=RenderKind.RECONSTRUCTION,
                    rate_hz=second.rate_hz,
                    weight=SECOND_ENDPOINT_WEIGHT,
                ),
                render_morph(first.latent, second.latent, weight=SECOND_ENDPOINT_WEIGHT, route=route),
            ),
            write_rendering(
                RenderedFile(
                    path=output_directory / "original_second.wav",
                    kind=RenderKind.ORIGINAL,
                    rate_hz=second.rate_hz,
                    weight=SECOND_ENDPOINT_WEIGHT,
                ),
                second.mono,
            ),
        ]
    )
    return MorphRenderSummary(first_hash=first.sample.hash, second_hash=second.sample.hash, files=tuple(files))


def decode_to_audio(latent: SampleLatent, *, route: MorphRoute) -> NDArray[np.float64]:
    """Carry a latent back to frames: decode it to an image, restore it, and estimate its phase."""
    return route.vocoder.synthesize(route.canonicalizer.restore(route.codec.decode(latent)))


def listening_set_manifest(description: MorphModelDescription, summary: MorphRenderSummary) -> str:
    """What a listening set is, as indented JSON written beside the audio.

    A set is judged by ear days after it was written, so the manifest names the two samples it runs
    between and the rate each file states, which is what it takes to render the same comparison
    again or to look either sample up in the catalog.
    """
    manifest = {
        "model": json.loads(description.model_dump_json()),
        "first_hash": summary.first_hash,
        "second_hash": summary.second_hash,
        "files": [
            {"name": file.path.name, "kind": str(file.kind), "rate_hz": file.rate_hz, "weight": file.weight}
            for file in summary.files
        ],
    }
    return json.dumps(manifest, indent=2)
