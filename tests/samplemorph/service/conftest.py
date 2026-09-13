from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import torch
from fastapi.testclient import TestClient
from trackmod.core.samples.depth import BitDepth

from samplecore.hashing import compute_sample_hash
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplemorph.geometry import log_frequency_geometry
from samplemorph.model_store import (
    DEFAULT_MODEL_NAME,
    PRINCIPAL_COMPONENT_CODEC_NAME,
    MorphModel,
    MorphModelDescription,
    model_path,
    save_model,
)
from samplemorph.pipeline import RouteChoice
from samplemorph.registries import (
    CANONICALIZER_REGISTRY,
    DEFAULT_CANONICALIZER_NAME,
    DEFAULT_MORPHER_NAME,
    PGHI_VOCODER_NAME,
    RESTORED_VOCODER_NAME,
)
from samplemorph.service.app import create_app
from samplemorph.service.settings import DEFAULT_INFERENCE_DEVICE, ServiceSettings
from samplemorph.training.principal_components import PrincipalComponentTrainer
from samplemorph.vocoders.restored import DEFAULT_RESTORER_NAME, RestorerDescription, restorer_path, save_restorer
from samplemorph.vocoders.restorer_model import Restorer, RestorerShape
from tests.samplemorph.conftest import harmonic_tone

TONES = ((220.0, 4096), (330.0, 8192), (440.0, 6144))
LATENT_SIZE = 2
SMALL_RESTORER = RestorerShape(channels=8, kernel_size=3, dilations=(1, 2))


@dataclass(frozen=True)
class StoredLibrary:
    """A library root holding three stored tones, a fitted linear codec, and an untrained restorer."""

    root: Path
    hashes: tuple[str, ...]
    frame_counts: tuple[int, ...]


def _store_tone(root: Path, *, frequency: float, frame_count: int) -> str:
    pcm = harmonic_tone(frame_count, frequency=frequency)
    sample_hash = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frame_count, pcm=pcm)
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frame_count)
    audio_store.write(root, SamplePCM(sample=sample, pcm=pcm))
    return sample_hash


def _fit_codec(root: Path) -> None:
    geometry = log_frequency_geometry()
    canonicalizer = CANONICALIZER_REGISTRY[DEFAULT_CANONICALIZER_NAME]()
    images = [
        canonicalizer.canonicalize(harmonic_tone(frame_count, frequency=frequency)) for frequency, frame_count in TONES
    ]
    codec = PrincipalComponentTrainer(geometry, latent_size=LATENT_SIZE, random_seed=0).fit(images)
    description = MorphModelDescription(
        codec=PRINCIPAL_COMPONENT_CODEC_NAME,
        canonicalizer=DEFAULT_CANONICALIZER_NAME,
        geometry=geometry,
        latent_size=LATENT_SIZE,
        fitted_sample_count=len(images),
        random_seed=0,
        explained_variance=codec.explained_variance,
    )
    save_model(model_path(root, name=DEFAULT_MODEL_NAME), MorphModel(description=description, codec=codec))


def _store_restorer(root: Path) -> None:
    torch.manual_seed(0)
    description = RestorerDescription(
        canonicalizer=DEFAULT_CANONICALIZER_NAME,
        geometry=log_frequency_geometry(),
        channels=SMALL_RESTORER.channels,
        kernel_size=SMALL_RESTORER.kernel_size,
        dilations=SMALL_RESTORER.dilations,
        epochs=1,
        trained_sample_count=len(TONES),
        best_validation_loss=0.05,
        least_squares_validation_loss=0.08,
    )
    save_restorer(restorer_path(root, name=DEFAULT_RESTORER_NAME), Restorer(SMALL_RESTORER), description)


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory) -> StoredLibrary:
    """Fitted once per module: the codec's fit and the band matrix's inverse are the slow parts."""
    root = tmp_path_factory.mktemp("library")
    hashes = tuple(_store_tone(root, frequency=frequency, frame_count=frame_count) for frequency, frame_count in TONES)
    _fit_codec(root)
    _store_restorer(root)
    return StoredLibrary(root=root, hashes=hashes, frame_counts=tuple(frame_count for _, frame_count in TONES))


def _settings(library: StoredLibrary, vocoder_name: str) -> ServiceSettings:
    return ServiceSettings(
        library_root=library.root,
        choice=RouteChoice(
            model_name=DEFAULT_MODEL_NAME,
            vocoder_name=vocoder_name,
            restorer_name=DEFAULT_RESTORER_NAME,
            morpher_name=DEFAULT_MORPHER_NAME,
            device=DEFAULT_INFERENCE_DEVICE,
        ),
    )


@pytest.fixture
def settings(library: StoredLibrary) -> ServiceSettings:
    return _settings(library, PGHI_VOCODER_NAME)


@pytest.fixture
def restored_settings(library: StoredLibrary) -> ServiceSettings:
    return _settings(library, RESTORED_VOCODER_NAME)


@pytest.fixture
def client(settings: ServiceSettings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
