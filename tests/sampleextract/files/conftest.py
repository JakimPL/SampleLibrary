from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import soundfile

from samplecore.config import LibraryConfig

RATE = 44100
SAMPLE_FRAMES = 1024
MINIMUM_SAMPLE_FRAMES = 512


@dataclass(frozen=True)
class SamplePack:
    """A folder of sample files laid out the way a commercial pack is, with the clutter one carries."""

    directory: Path
    kick: Path
    second_kick: Path
    loop: Path
    too_short: Path


def _write_tone(path: Path, *, frames: int, channels: int, seed: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    waveform = np.random.default_rng(seed).uniform(-0.9, 0.9, (frames, channels))
    soundfile.write(path, waveform, RATE, subtype="PCM_16")
    return path


@pytest.fixture
def sample_pack(tmp_path: Path) -> SamplePack:
    directory = tmp_path / "packs"
    pack = SamplePack(
        directory=directory,
        kick=_write_tone(directory / "Kicks" / "Kick 01.wav", frames=SAMPLE_FRAMES, channels=1, seed=1),
        second_kick=_write_tone(directory / "Kicks" / "Kick 02.flac", frames=SAMPLE_FRAMES, channels=1, seed=2),
        loop=_write_tone(directory / "LOOPS" / "Loop 01.wav", frames=SAMPLE_FRAMES * 4, channels=2, seed=3),
        too_short=_write_tone(directory / "Kicks" / "Click.wav", frames=MINIMUM_SAMPLE_FRAMES // 2, channels=1, seed=4),
    )
    (directory / "Kicks" / "._Kick 01.wav").write_bytes(b"a resource fork")
    (directory / "Kicks" / "Kick 01.asd").write_bytes(b"an analysis file")
    (directory / "README.txt").write_text("thank you for your purchase", encoding="utf-8")
    return pack


@pytest.fixture
def files_config(tmp_path: Path, _database_url: str, sample_pack: SamplePack) -> LibraryConfig:
    return LibraryConfig(
        module_source_directory=tmp_path / "modules",
        library_root=tmp_path / "library",
        database_url=_database_url,
        minimum_sample_frames=MINIMUM_SAMPLE_FRAMES,
        sample_directories=(sample_pack.directory,),
    )
