from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import soundfile
from fastapi.testclient import TestClient
from trackmod.core.samples.depth import BitDepth

from samplecore.hashing import compute_sample_hash
from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage import audio_store
from samplemorph.envelope.settings import EnvelopeSettings, Excitation
from samplemorph.routes.selection import Glide, RouteSelection
from samplemorph.service.app import create_app
from samplemorph.service.renderer import load_renderer
from samplemorph.service.settings import ServiceSettings
from tests.samplemorph.conftest import harmonic_tone

TONES = ((220.0, 4096), (330.0, 8192), (440.0, 6144))
FILTER_COEFFICIENT_COUNT = 24
FILE_TONE = (275.0, 5120)
FILE_RATE_HZ = 44100


@dataclass(frozen=True)
class StoredLibrary:
    """A library root holding three stored tones, beside a sample directory holding a fourth tone as a file read in place."""

    root: Path
    hashes: tuple[str, ...]
    frame_counts: tuple[int, ...]
    sample_directory: Path
    file_path: Path
    file_hash: str


def _store_tone(root: Path, *, frequency: float, frame_count: int) -> str:
    pcm = harmonic_tone(frame_count, frequency=frequency)
    sample_hash = compute_sample_hash(depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frame_count, pcm=pcm)
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=frame_count)
    audio_store.write(root, SamplePCM(sample=sample, pcm=pcm))
    return sample_hash


def _write_tone_file(path: Path, *, frequency: float, frame_count: int) -> str:
    path.parent.mkdir(parents=True)
    soundfile.write(path, harmonic_tone(frame_count, frequency=frequency), FILE_RATE_HZ, subtype="PCM_16")
    return decode_sample_file(path).sample_pcm.sample.hash


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory) -> StoredLibrary:
    """Stored once per module, since every test reads the same tones."""
    root = tmp_path_factory.mktemp("library")
    hashes = tuple(_store_tone(root, frequency=frequency, frame_count=frame_count) for frequency, frame_count in TONES)
    sample_directory = tmp_path_factory.mktemp("packs")
    file_path = sample_directory / "Tones" / "Tone 01.wav"
    return StoredLibrary(
        root=root,
        hashes=hashes,
        frame_counts=tuple(frame_count for _, frame_count in TONES),
        sample_directory=sample_directory,
        file_path=file_path,
        file_hash=_write_tone_file(file_path, frequency=FILE_TONE[0], frame_count=FILE_TONE[1]),
    )


def _settings(library: StoredLibrary, *, selection: RouteSelection) -> ServiceSettings:
    """One process, rendering what the selection names and handing over filters drawn by their own count of cosines."""
    return ServiceSettings(
        library_root=library.root,
        sample_directories=(library.sample_directory,),
        selection=selection,
        filter_selection=RouteSelection(envelope=EnvelopeSettings(coefficient_count=FILTER_COEFFICIENT_COUNT)),
    )


@pytest.fixture
def settings(library: StoredLibrary) -> ServiceSettings:
    """The envelope route sounding the first tone's excitation, which holds its pitch and so has a filter form."""
    return _settings(library, selection=RouteSelection(envelope=EnvelopeSettings(excitation=Excitation.FIRST)))


@pytest.fixture
def gliding_settings(library: StoredLibrary) -> ServiceSettings:
    """The envelope route crossfading both excitations and gliding their pitch, as the committed selection does."""
    return _settings(
        library,
        selection=RouteSelection(envelope=EnvelopeSettings(excitation=Excitation.BOTH), glide=Glide.SUBHARMONIC),
    )


@pytest.fixture
def client(settings: ServiceSettings) -> Iterator[TestClient]:
    with TestClient(create_app(load_renderer(settings))) as test_client:
        yield test_client
