from __future__ import annotations

import multiprocessing
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel
from threadpoolctl import threadpool_limits
from tqdm import tqdm

from samplecore.models.base import FROZEN
from samplecore.models.sample import Sample
from samplecore.storage import audio_store
from samplecore.waveform import resample_by_semitones
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.descriptors.pooling import canonical_duration, pool_bands, pooled_band_count
from samplemorph.geometry import Geometry
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.training.phase_data import WORKER_START_METHOD

CACHE_DIRECTORY_NAME: Final[str] = "cache"
GRID_CACHE_DIRECTORY_NAME: Final[str] = "grids"
DEFAULT_GRID_CACHE_NAME: Final[str] = "descriptor"
DEFAULT_RETUNED_VIEW_COUNT: Final[int] = 2
# The corpus retunes a sample by an octave at the median and seventeen semitones at the ninetieth
# percentile, so views drawn this far teach the invariance the catalog itself asks for.
DEFAULT_VIEW_RANGE_SEMITONES: Final[float] = 17.0
GRIDS_FILE_NAME: Final[str] = "grids.npy"
DURATIONS_FILE_NAME: Final[str] = "durations.npy"
HASHES_FILE_NAME: Final[str] = "hashes.txt"
DESCRIPTION_FILE_NAME: Final[str] = "description.json"
JOB_CHUNK_SIZE: Final[int] = 8


class GridCacheDescription(BaseModel):
    """What a grid cache holds, so a trainer can tell whether it is the one it wants."""

    model_config = FROZEN

    canonicalizer: str
    geometry: Geometry
    bands_per_semitone: int
    band_count: int
    time_columns: int
    sample_count: int
    view_count: int
    view_range_semitones: float
    random_seed: int


@dataclass(frozen=True)
class GridCache:
    """Every sample of a draw as its pooled canonical grid, stored once and read every epoch.

    `grids` is `(samples, 1 + views, bands, columns)`: the stored waveform's grid first, then the
    same sound read at each of its retunings. `durations` holds each grid's canonical duration in
    the same order. The retuned views are what teach a descriptor that a retuning changes nothing,
    and they are drawn once so every epoch and every run reads the same views.
    """

    directory: Path
    description: GridCacheDescription
    hashes: tuple[str, ...]
    grids: NDArray[np.float16]
    durations: NDArray[np.float32]

    @property
    def sample_count(self) -> int:
        return len(self.hashes)

    @property
    def view_count(self) -> int:
        return self.description.view_count


@dataclass(frozen=True)
class GridCacheRecipe:
    """What one cache is built from: the axis, the pooling, and the views each sample gets."""

    canonicalizer_name: str
    bands_per_semitone: int
    view_count: int
    view_range_semitones: float
    random_seed: int


@dataclass(frozen=True)
class _Job:
    sample: Sample
    offsets: tuple[float, ...]


def grid_cache_directory(library_root: Path, *, name: str) -> Path:
    """Where one named cache lives, under the library root beside the models and the runs."""
    return library_root / CACHE_DIRECTORY_NAME / GRID_CACHE_DIRECTORY_NAME / name


def build_grid_cache(
    directory: Path,
    *,
    samples: tuple[Sample, ...],
    library_root: Path,
    recipe: GridCacheRecipe,
    worker_count: int,
) -> GridCache:
    """Canonicalize every sample and its retuned views into a memory-mapped file under `directory`.

    The work runs in fresh worker processes, each held to one thread, which is the shape the phase
    trainer measured as the one that shares the machine's cores rather than fighting over them.
    Rows are written as they arrive, so memory stays flat however large the draw.

    Raises:
        ValueError: the draw is empty.
    """
    if not samples:
        raise ValueError("a grid cache needs at least one sample to hold")

    geometry = CANONICALIZER_REGISTRY[recipe.canonicalizer_name]().geometry
    band_count = pooled_band_count(geometry, bands_per_semitone=recipe.bands_per_semitone)
    description = GridCacheDescription(
        canonicalizer=recipe.canonicalizer_name,
        geometry=geometry,
        bands_per_semitone=recipe.bands_per_semitone,
        band_count=band_count,
        time_columns=geometry.time_columns,
        sample_count=len(samples),
        view_count=recipe.view_count,
        view_range_semitones=recipe.view_range_semitones,
        random_seed=recipe.random_seed,
    )
    directory.mkdir(parents=True, exist_ok=True)
    grids = np.lib.format.open_memmap(
        directory / GRIDS_FILE_NAME,
        mode="w+",
        dtype=np.float16,
        shape=(len(samples), 1 + recipe.view_count, band_count, geometry.time_columns),
    )
    durations = np.zeros((len(samples), 1 + recipe.view_count), dtype=np.float32)
    generator = np.random.default_rng(recipe.random_seed)
    jobs = [
        _Job(
            sample=sample,
            offsets=tuple(
                generator.uniform(-recipe.view_range_semitones, recipe.view_range_semitones, recipe.view_count).tolist()
            ),
        )
        for sample in samples
    ]
    worker = _Worker(library_root=library_root, canonicalizer_name=recipe.canonicalizer_name, band_count=band_count)
    for position, (job_grids, job_durations) in enumerate(_derived(jobs, worker=worker, worker_count=worker_count)):
        grids[position] = job_grids
        durations[position] = job_durations
    grids.flush()
    np.save(directory / DURATIONS_FILE_NAME, durations)
    (directory / HASHES_FILE_NAME).write_text("\n".join(sample.hash for sample in samples), encoding="utf-8")
    (directory / DESCRIPTION_FILE_NAME).write_text(description.model_dump_json(indent=2), encoding="utf-8")
    return open_grid_cache(directory)


def open_grid_cache(directory: Path) -> GridCache:
    """Read a built cache back, mapping the grids rather than loading them.

    Raises:
        FileNotFoundError: no cache was built under that directory.
    """
    description_path = directory / DESCRIPTION_FILE_NAME
    if not description_path.exists():
        raise FileNotFoundError(f"no grid cache is built under {directory}")

    description = GridCacheDescription.model_validate_json(description_path.read_text(encoding="utf-8"))
    hashes = tuple(directory.joinpath(HASHES_FILE_NAME).read_text(encoding="utf-8").split("\n"))
    return GridCache(
        directory=directory,
        description=description,
        hashes=hashes,
        grids=np.load(directory / GRIDS_FILE_NAME, mmap_mode="r"),
        durations=np.load(directory / DURATIONS_FILE_NAME),
    )


def _derived(
    jobs: list[_Job], *, worker: _Worker, worker_count: int
) -> Iterator[tuple[NDArray[np.float16], NDArray[np.float32]]]:
    """Each job's grids in order, from a pool of fresh processes or, with none asked for, in this one."""
    progress = tqdm(total=len(jobs), desc="Canonicalizing", unit="sample")
    if worker_count == 0:
        for job in jobs:
            yield worker(job)
            progress.update()
    else:
        with multiprocessing.get_context(WORKER_START_METHOD).Pool(worker_count, initializer=_limit_threads) as pool:
            for result in pool.imap(worker, jobs, chunksize=JOB_CHUNK_SIZE):
                yield result
                progress.update()
    progress.close()


def _limit_threads() -> None:
    """One thread per worker, so a dozen of them share the cores rather than contend for all of them."""
    threadpool_limits(limits=1)


@dataclass(frozen=True)
class _Worker:
    """Derives one sample's stored grid and its retuned views; built once and sent to every process."""

    library_root: Path
    canonicalizer_name: str
    band_count: int

    def __call__(self, job: _Job) -> tuple[NDArray[np.float16], NDArray[np.float32]]:
        canonicalizer = CANONICALIZER_REGISTRY[self.canonicalizer_name]()
        mono = prepare_mono(audio_store.read(self.library_root, job.sample).pcm)
        readings = [mono] + [resample_by_semitones(mono, semitones=offset) for offset in job.offsets]
        grids = []
        durations = []
        for reading in readings:
            image = canonicalizer.canonicalize(reading)
            grids.append(pool_bands(image.grid, band_count=self.band_count).astype(np.float16))
            durations.append(canonical_duration(image.conditioners))
        return np.stack(grids), np.asarray(durations, dtype=np.float32)
