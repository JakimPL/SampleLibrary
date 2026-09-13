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
from samplecore.waveform import heard_at_rate
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.codecs import SampleCodec
from samplemorph.images import SampleLatent
from samplemorph.model_store import MorphModel, MorphModelDescription, load_named_model
from samplemorph.morphers import Morpher, MorphWeights
from samplemorph.registries import MORPHER_REGISTRY, canonicalizer_for_geometry
from samplemorph.rendering import RenderedFile, RenderKind, write_rendering
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
class HeardSample:
    """One catalog sample as the library plays it: its stored frames, and the rate they are read at."""

    sample: Sample
    pcm: NDArray[np.float64]
    rate_hz: float


@dataclass(frozen=True)
class EncodedSample:
    """One catalog sample carried into the latent space as stored, with what it takes to hear it again."""

    sample: Sample
    latent: SampleLatent
    mono: NDArray[np.float64]
    rate_hz: float


@dataclass(frozen=True)
class EncodedPair:
    """Two heard samples carried into one latent space, in the frame of the rate the pair is heard at.

    Each latent describes its sample resampled to `rate_hz`, so a render at any weight plays at
    that one rate, and each end sounds at the pitch and for the length the library plays it at.
    """

    first: HeardSample
    second: HeardSample
    first_latent: SampleLatent
    second_latent: SampleLatent
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


def encode_heard(
    pcm: NDArray[np.float64],
    *,
    rate_hz: float,
    target_rate_hz: float,
    canonicalizer: Canonicalizer,
    codec: SampleCodec,
) -> EncodedWaveform:
    """Carry stored frames heard at `rate_hz` into the latent space in the frame of `target_rate_hz`.

    The frames are resampled so that, played at the target rate, they are the sound the library
    plays at `rate_hz`; a target equal to the heard rate carries them as they are.
    """
    return encode_waveform(
        heard_at_rate(pcm, playback_rate_hz=rate_hz, stored_rate_hz=target_rate_hz),
        canonicalizer=canonicalizer,
        codec=codec,
    )


def common_rate(first_rate_hz: float, second_rate_hz: float) -> float:
    """The rate a pair is carried into one frame at: the higher of the two.

    The faster sample keeps every band it has and the slower one gains frames and loses nothing,
    which no rate between the two could promise for the faster one.
    """
    return max(first_rate_hz, second_rate_hz)


def read_heard_sample(connection: Connection, library_root: Path, sample: Sample) -> HeardSample:
    """Read one cataloged sample with the rate the application plays it at.

    The stored file states a nominal rate rather than a measured one, so the rate is read from the
    catalog by the one rule every reader applies: what the note events say first, the occurrences'
    dominant rate after.

    Raises:
        ValueError: the catalog holds no occurrence of this sample, so no playback rate is known.
    """
    rate = resolved_playback_rates(connection, [sample.hash])[sample.hash]
    if rate is None:
        raise ValueError(f"sample {sample.hash} has no cataloged occurrence, so its playback rate is unknown")

    return HeardSample(sample=sample, pcm=audio_store.read(library_root, sample).pcm, rate_hz=float(rate))


def encode_sample(
    connection: Connection,
    library_root: Path,
    sample: Sample,
    *,
    canonicalizer: Canonicalizer,
    codec: SampleCodec,
) -> EncodedSample:
    """Read one cataloged sample and encode it as stored, for measuring it against itself.

    The playback rate travels alongside so a rendered file can state the rate its content is heard at.

    Raises:
        ValueError: the catalog holds no occurrence of this sample, so no playback rate is known.
    """
    heard = read_heard_sample(connection, library_root, sample)
    encoded = encode_waveform(heard.pcm, canonicalizer=canonicalizer, codec=codec)
    return EncodedSample(sample=sample, latent=encoded.latent, mono=encoded.mono, rate_hz=heard.rate_hz)


def encode_pair(
    first: HeardSample, second: HeardSample, *, canonicalizer: Canonicalizer, codec: SampleCodec
) -> EncodedPair:
    """Carry two heard samples into one latent space, in the frame of the rate the pair is heard at."""
    rate_hz = common_rate(first.rate_hz, second.rate_hz)
    return EncodedPair(
        first=first,
        second=second,
        first_latent=encode_heard(
            first.pcm, rate_hz=first.rate_hz, target_rate_hz=rate_hz, canonicalizer=canonicalizer, codec=codec
        ).latent,
        second_latent=encode_heard(
            second.pcm, rate_hz=second.rate_hz, target_rate_hz=rate_hz, canonicalizer=canonicalizer, codec=codec
        ).latent,
        rate_hz=rate_hz,
    )


def render_morph(first: SampleLatent, second: SampleLatent, *, weight: float, route: MorphRoute) -> NDArray[np.float64]:
    """The audio at one weight between two latents: morph, decode, restore, and estimate the phase.

    At weight 0 or 1 the morpher returns an endpoint's own latent, so the same call renders a
    sample's reconstruction and every point between two.
    """
    return decode_to_audio(route.morpher.morph(first, second, weights=MorphWeights.uniform(weight)), route=route)


def render_listening_set(
    pair: EncodedPair,
    *,
    route: MorphRoute,
    output_directory: Path,
    weights: tuple[float, ...] = DEFAULT_MORPH_WEIGHTS,
) -> MorphRenderSummary:
    """Write both originals, both reconstructions, and one file per morph weight.

    The originals are written at their own rates beside the reconstructions on purpose: without
    hearing the untouched audio, a listener cannot tell a codec that lost something from a sample
    that always sounded that way. The reconstructions and the morphs state the one rate the pair
    is heard at, so every point of the path, its ends included, sounds through the same frame.
    """
    files = [
        write_rendering(
            RenderedFile(
                path=output_directory / "original_first.wav",
                kind=RenderKind.ORIGINAL,
                rate_hz=pair.first.rate_hz,
                weight=FIRST_ENDPOINT_WEIGHT,
            ),
            prepare_mono(pair.first.pcm),
        ),
        write_rendering(
            RenderedFile(
                path=output_directory / "reconstruction_first.wav",
                kind=RenderKind.RECONSTRUCTION,
                rate_hz=pair.rate_hz,
                weight=FIRST_ENDPOINT_WEIGHT,
            ),
            render_morph(pair.first_latent, pair.second_latent, weight=FIRST_ENDPOINT_WEIGHT, route=route),
        ),
    ]
    for weight in weights:
        files.append(
            write_rendering(
                RenderedFile(
                    path=output_directory / f"morph_{int(round(weight * 100)):03d}.wav",
                    kind=RenderKind.MORPH,
                    rate_hz=pair.rate_hz,
                    weight=weight,
                ),
                render_morph(pair.first_latent, pair.second_latent, weight=weight, route=route),
            )
        )
    files.extend(
        [
            write_rendering(
                RenderedFile(
                    path=output_directory / "reconstruction_second.wav",
                    kind=RenderKind.RECONSTRUCTION,
                    rate_hz=pair.rate_hz,
                    weight=SECOND_ENDPOINT_WEIGHT,
                ),
                render_morph(pair.first_latent, pair.second_latent, weight=SECOND_ENDPOINT_WEIGHT, route=route),
            ),
            write_rendering(
                RenderedFile(
                    path=output_directory / "original_second.wav",
                    kind=RenderKind.ORIGINAL,
                    rate_hz=pair.second.rate_hz,
                    weight=SECOND_ENDPOINT_WEIGHT,
                ),
                prepare_mono(pair.second.pcm),
            ),
        ]
    )
    return MorphRenderSummary(
        first_hash=pair.first.sample.hash, second_hash=pair.second.sample.hash, files=tuple(files)
    )


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
