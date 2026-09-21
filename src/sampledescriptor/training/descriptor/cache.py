from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.sample import Sample
from samplecore.storage.sample_audio import SampleAudio
from sampledescriptor.descriptors.pooling import canonical_duration, pool_bands, pooled_band_count
from sampledescriptor.descriptors.views import retuned_view
from sampledescriptor.geometry import Anchor, GridGeometry
from sampledescriptor.registries import CANONICALIZER_REGISTRY, canonicalizer_for_geometry
from sampledescriptor.training.cache_staging import CACHE_DIRECTORY_NAME, fresh_staging, publish_staged
from sampledescriptor.training.processes import mapped_in_processes
from samplemorph.canonicalizers.common import prepare_mono

GRID_CACHE_DIRECTORY_NAME: Final[str] = "grids"
DEFAULT_GRID_CACHE_NAME: Final[str] = "descriptor"
# The first reading of every sample is the stored waveform's own; the retuned views follow it.
STORED_VIEW: Final[int] = 0
DEFAULT_RETUNED_VIEW_COUNT: Final[int] = 2
MINIMUM_RETUNED_VIEW_COUNT: Final[int] = 1
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
    geometry: GridGeometry
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
    same sound read at each of its retunings. `durations` holds each sample's canonical duration
    beside every one of its grids. The retuned views are what teach a descriptor that a retuning
    changes nothing; they are stored once, and a trainer draws which of them pairs with the stored
    grid every epoch.
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
class GridSource:
    """What a reading set needs to know about a cache without holding its mapped grids.

    A worker started fresh maps the file itself from the directory, so handing it this rather than
    the cache keeps the grids out of what is sent to every process. The shape the trainer opened
    travels too, so a worker that maps a cache rebuilt in the meantime notices.
    """

    directory: Path
    durations: NDArray[np.float32]
    view_count: int
    grid_shape: tuple[int, ...]

    @classmethod
    def of(cls, cache: GridCache) -> GridSource:
        return cls(
            directory=cache.directory,
            durations=cache.durations,
            view_count=cache.view_count,
            grid_shape=tuple(cache.grids.shape),
        )


class MappedGrids:
    """A cache's grids, mapped on first use in whichever process reads them."""

    def __init__(self, source: GridSource) -> None:
        self._source = source
        self._grids: NDArray[np.float16] | None = None

    def array(self) -> NDArray[np.float16]:
        """The mapped grids.

        Raises:
            ValueError: the file under the cache's directory is no longer the cache the run opened.
        """
        if self._grids is None:
            grids: NDArray[np.float16] = np.load(self._source.directory / GRIDS_FILE_NAME, mmap_mode="r")
            if tuple(grids.shape) != self._source.grid_shape:
                raise ValueError(
                    f"the grid cache under {self._source.directory} was rebuilt while this run read it; "
                    "start the run again"
                )
            self._grids = grids
        return self._grids


@dataclass(frozen=True)
class GridCacheRecipe:
    """What one cache is built from: the axis, the pooling, and the views each sample gets."""

    canonicalizer_name: str
    anchor: Anchor
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
    audio: SampleAudio,
    recipe: GridCacheRecipe,
    worker_count: int,
) -> GridCache:
    """Canonicalize every sample and its retuned views into a memory-mapped file under `directory`.

    The work runs in fresh worker processes, each held to one thread, which is the shape the phase
    trainer measured as the one that shares the machine's cores rather than fighting over them.
    Rows are written as they arrive, so memory stays flat however large the draw.

    The cache is built beside `directory` and moved into place once its description is written,
    through `publish_staged`. The rows are sized to `samples`, so a caller passes the samples whose
    audio can be read now; a sample file going missing while the build runs stops the build the same
    way.

    Raises:
        ValueError: the draw is empty.
    """
    if not samples:
        raise ValueError("a grid cache needs at least one sample to hold")

    geometry = CANONICALIZER_REGISTRY[recipe.canonicalizer_name](anchor=recipe.anchor).geometry
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
    staging = fresh_staging(directory)
    grids = np.lib.format.open_memmap(
        staging / GRIDS_FILE_NAME,
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
    worker = _Worker(audio=audio, geometry=geometry, band_count=band_count)
    derived = mapped_in_processes(
        worker, jobs, worker_count=worker_count, chunk_size=JOB_CHUNK_SIZE, description="Canonicalizing"
    )
    for position, (job_grids, job_durations) in enumerate(derived):
        grids[position] = job_grids
        durations[position] = job_durations
    grids.flush()
    del grids
    np.save(staging / DURATIONS_FILE_NAME, durations)
    (staging / HASHES_FILE_NAME).write_text("\n".join(sample.hash for sample in samples), encoding="utf-8")
    (staging / DESCRIPTION_FILE_NAME).write_text(description.model_dump_json(indent=2), encoding="utf-8")
    publish_staged(
        staging, directory, file_names=(GRIDS_FILE_NAME, DURATIONS_FILE_NAME, HASHES_FILE_NAME, DESCRIPTION_FILE_NAME)
    )
    return open_grid_cache(directory)


def open_grid_cache(directory: Path) -> GridCache:
    """Read a built cache back, mapping the grids rather than loading them.

    Raises:
        FileNotFoundError: no cache was built under that directory.
        ValueError: the grids, the durations and the hashes disagree on how many samples and views
            the cache holds.
    """
    description_path = directory / DESCRIPTION_FILE_NAME
    if not description_path.exists():
        raise FileNotFoundError(f"no grid cache is built under {directory}")

    description = GridCacheDescription.model_validate_json(description_path.read_text(encoding="utf-8"))
    hashes = tuple(directory.joinpath(HASHES_FILE_NAME).read_text(encoding="utf-8").split("\n"))
    grids: NDArray[np.float16] = np.load(directory / GRIDS_FILE_NAME, mmap_mode="r")
    durations: NDArray[np.float32] = np.load(directory / DURATIONS_FILE_NAME)
    expected_grids = (
        description.sample_count,
        1 + description.view_count,
        description.band_count,
        description.time_columns,
    )
    if (
        tuple(grids.shape) != expected_grids
        or tuple(durations.shape) != expected_grids[:2]
        or len(hashes) != description.sample_count
    ):
        raise ValueError(
            f"the grid cache under {directory} is incomplete: its grids, durations and hashes disagree with its "
            "description; build it again with cache-grids"
        )
    return GridCache(directory=directory, description=description, hashes=hashes, grids=grids, durations=durations)


@dataclass(frozen=True)
class _Worker:
    """Derives one sample's stored grid and its retuned views; built once and sent to every process.

    Every view records the sample's own duration. A view is the same sound read at another rate,
    and the duration a descriptor hears beside it is the sound's, so the two readings of one sound
    differ in their grids alone.
    """

    audio: SampleAudio
    geometry: GridGeometry
    band_count: int

    def __call__(self, job: _Job) -> tuple[NDArray[np.float16], NDArray[np.float32]]:
        canonicalizer = canonicalizer_for_geometry(self.geometry)
        mono = prepare_mono(self.audio.read(job.sample).pcm)
        stored = canonicalizer.canonicalize(mono)
        views = [retuned_view(mono, semitones=offset, canonicalizer=canonicalizer) for offset in job.offsets]
        grids = [pool_bands(image.grid, band_count=self.band_count).astype(np.float16) for image in (stored, *views)]
        duration = canonical_duration(stored.conditioners)
        return np.stack(grids), np.full(1 + len(views), duration, dtype=np.float32)
