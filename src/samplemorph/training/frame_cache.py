from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplecore.models.sample import Sample
from samplecore.storage.sample_audio import SampleAudio
from samplecore.waveform import resample_by_semitones
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.coordinates.frames import FrameAnalysis, constant_q_frames
from samplemorph.training.cache_staging import CACHE_DIRECTORY_NAME, fresh_staging, publish_staged
from samplemorph.training.processes import mapped_in_processes

FRAME_CACHE_DIRECTORY_NAME: Final[str] = "frames"
DEFAULT_FRAME_CACHE_NAME: Final[str] = "pitch"
# Every sample is read as stored and once retuned, at an offset saved beside it.
STORED_READING: Final[int] = 0
RETUNED_READING: Final[int] = 1
READING_COUNT: Final[int] = 2
# The corpus retunes a sample by seventeen semitones at the ninetieth percentile.
DEFAULT_RETUNING_RANGE_SEMITONES: Final[float] = 17.0
FRAMES_FILE_NAME: Final[str] = "frames.npy"
COUNTS_FILE_NAME: Final[str] = "counts.npy"
OFFSETS_FILE_NAME: Final[str] = "offsets.npy"
HASHES_FILE_NAME: Final[str] = "hashes.txt"
DESCRIPTION_FILE_NAME: Final[str] = "description.json"
JOB_CHUNK_SIZE: Final[int] = 8


class FrameCacheDescription(BaseModel):
    """What a frame cache holds, so a trainer can tell whether it reads the frames it wants."""

    model_config = FROZEN

    analysis: FrameAnalysis
    sample_count: int = Field(gt=0)
    retuning_range_semitones: float = Field(ge=0.0)
    random_seed: int


@dataclass(frozen=True)
class FrameCache:
    """Every sample of a draw as its kept constant-Q frames, as stored and once truly retuned.

    `frames` is `(samples, readings, kept frames, bands)`: the stored waveform's frames first, then
    the frames of the same waveform resampled by its offset in `offsets`. `counts` says how many
    frames each reading kept; the rows past a reading's count are silence. The retuned reading is a
    real resampling, so it tells a model's shift of the analysis apart from a sound's retuning.
    """

    directory: Path
    description: FrameCacheDescription
    hashes: tuple[str, ...]
    frames: NDArray[np.float16]
    counts: NDArray[np.int16]
    offsets: NDArray[np.float32]

    @property
    def sample_count(self) -> int:
        return len(self.hashes)


@dataclass(frozen=True)
class FrameCacheRecipe:
    """What one frame cache is built from: the analysis, and how far the retuned reading may sit."""

    analysis: FrameAnalysis
    retuning_range_semitones: float
    random_seed: int


@dataclass(frozen=True)
class _Job:
    sample: Sample
    offset_semitones: float


def frame_cache_directory(library_root: Path, *, name: str) -> Path:
    """Where one named frame cache lives, under the library root beside the grid caches."""
    return library_root / CACHE_DIRECTORY_NAME / FRAME_CACHE_DIRECTORY_NAME / name


def build_frame_cache(
    directory: Path,
    *,
    samples: tuple[Sample, ...],
    audio: SampleAudio,
    recipe: FrameCacheRecipe,
    worker_count: int,
) -> FrameCache:
    """Read every sample and one retuning of it as constant-Q frames into a memory-mapped file under `directory`.

    The work runs in fresh worker processes, each held to one thread, and rows are written as they
    arrive, so memory stays flat however large the draw. The cache is built beside `directory` and
    moved into place through `publish_staged` once its description is written.

    Raises:
        ValueError: the draw is empty.
    """
    if not samples:
        raise ValueError("a frame cache needs at least one sample to hold")

    analysis = recipe.analysis
    description = FrameCacheDescription(
        analysis=analysis,
        sample_count=len(samples),
        retuning_range_semitones=recipe.retuning_range_semitones,
        random_seed=recipe.random_seed,
    )
    staging = fresh_staging(directory)
    frames = np.lib.format.open_memmap(
        staging / FRAMES_FILE_NAME,
        mode="w+",
        dtype=np.float16,
        shape=(len(samples), READING_COUNT, analysis.kept_frame_count, analysis.band_count),
    )
    counts = np.zeros((len(samples), READING_COUNT), dtype=np.int16)
    offsets = np.random.default_rng(recipe.random_seed).uniform(
        -recipe.retuning_range_semitones, recipe.retuning_range_semitones, len(samples)
    )
    jobs = [
        _Job(sample=sample, offset_semitones=float(offset)) for sample, offset in zip(samples, offsets, strict=True)
    ]
    derived = mapped_in_processes(
        _Worker(audio=audio, analysis=analysis),
        jobs,
        worker_count=worker_count,
        chunk_size=JOB_CHUNK_SIZE,
        description="Reading frames",
    )
    for position, (job_frames, job_counts) in enumerate(derived):
        frames[position] = job_frames
        counts[position] = job_counts
    frames.flush()
    del frames
    np.save(staging / COUNTS_FILE_NAME, counts)
    np.save(staging / OFFSETS_FILE_NAME, offsets.astype(np.float32))
    (staging / HASHES_FILE_NAME).write_text("\n".join(sample.hash for sample in samples), encoding="utf-8")
    (staging / DESCRIPTION_FILE_NAME).write_text(description.model_dump_json(indent=2), encoding="utf-8")
    publish_staged(
        staging,
        directory,
        file_names=(FRAMES_FILE_NAME, COUNTS_FILE_NAME, OFFSETS_FILE_NAME, HASHES_FILE_NAME, DESCRIPTION_FILE_NAME),
    )
    return open_frame_cache(directory)


def open_frame_cache(directory: Path) -> FrameCache:
    """Read a built frame cache back, mapping the frames rather than loading them.

    Raises:
        FileNotFoundError: no frame cache was built under that directory.
        ValueError: the frames, counts, offsets and hashes disagree with the description.
    """
    description_path = directory / DESCRIPTION_FILE_NAME
    if not description_path.exists():
        raise FileNotFoundError(f"no frame cache is built under {directory}")

    description = FrameCacheDescription.model_validate_json(description_path.read_text(encoding="utf-8"))
    hashes = tuple(directory.joinpath(HASHES_FILE_NAME).read_text(encoding="utf-8").split("\n"))
    frames: NDArray[np.float16] = np.load(directory / FRAMES_FILE_NAME, mmap_mode="r")
    counts: NDArray[np.int16] = np.load(directory / COUNTS_FILE_NAME)
    offsets: NDArray[np.float32] = np.load(directory / OFFSETS_FILE_NAME)
    expected_frames = (
        description.sample_count,
        READING_COUNT,
        description.analysis.kept_frame_count,
        description.analysis.band_count,
    )
    if (
        tuple(frames.shape) != expected_frames
        or tuple(counts.shape) != expected_frames[:2]
        or tuple(offsets.shape) != expected_frames[:1]
        or len(hashes) != description.sample_count
    ):
        raise ValueError(
            f"the frame cache under {directory} is incomplete: its frames, counts, offsets and hashes disagree with "
            "its description; build it again with cache-frames"
        )
    return FrameCache(
        directory=directory, description=description, hashes=hashes, frames=frames, counts=counts, offsets=offsets
    )


@dataclass(frozen=True)
class _Worker:
    """Reads one sample's frames as stored and at its retuning; built once and sent to every process."""

    audio: SampleAudio
    analysis: FrameAnalysis

    def __call__(self, job: _Job) -> tuple[NDArray[np.float16], NDArray[np.int16]]:
        mono = prepare_mono(self.audio.read(job.sample).pcm)
        retuned = PreparedMono(resample_by_semitones(mono, semitones=job.offset_semitones))
        rows = np.zeros((READING_COUNT, self.analysis.kept_frame_count, self.analysis.band_count), dtype=np.float16)
        counts = np.zeros(READING_COUNT, dtype=np.int16)
        for reading, waveform in ((STORED_READING, mono), (RETUNED_READING, retuned)):
            kept = constant_q_frames(waveform, analysis=self.analysis)
            rows[reading, : kept.shape[0]] = kept
            counts[reading] = kept.shape[0]
        return rows, counts
