from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.sample_audio import SampleAudio
from sampledescriptor.geometry import Anchor
from sampledescriptor.training.descriptor import cache as descriptor_cache
from sampledescriptor.training.descriptor.cache import (
    HASHES_FILE_NAME,
    GridCacheRecipe,
    GridSource,
    MappedGrids,
    build_grid_cache,
    open_grid_cache,
)
from tests.sampledescriptor.training.conftest import write_grid_cache
from tests.samplemorph.conftest import harmonic_tone

FRAME_COUNT = 8192
SAMPLE_COUNT = 5
STOPPED_AFTER = 2
CANONICALIZE = descriptor_cache._Worker.__call__


class _BrokenWorker(RuntimeError):
    pass


def _samples(library_root: Path, count: int) -> tuple[Sample, ...]:
    samples = []
    for index in range(count):
        sample = Sample(
            hash=format(index + 1, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=FRAME_COUNT
        )
        audio_store.write(
            library_root, SamplePCM(sample=sample, pcm=harmonic_tone(FRAME_COUNT, frequency=110.0 * (index + 1)))
        )
        samples.append(sample)
    return tuple(samples)


def _recipe(*, random_seed: int = 0) -> GridCacheRecipe:
    return GridCacheRecipe(
        canonicalizer_name="log_frequency",
        anchor=Anchor.NONE,
        bands_per_semitone=1,
        view_count=1,
        view_range_semitones=2.0,
        random_seed=random_seed,
    )


@dataclass
class CountedWorker:
    """Canonicalizes as the cache's own worker does, naming each sample it reads, and stops before the one it is told to."""

    stop_before: int | None
    canonicalized: list[str] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        counted = self

        def call(worker: descriptor_cache._Worker, job: descriptor_cache._Job) -> object:
            if len(counted.canonicalized) == counted.stop_before:
                raise _BrokenWorker("stopped partway")
            counted.canonicalized.append(job.sample.hash)
            return CANONICALIZE(worker, job)

        monkeypatch.setattr(descriptor_cache._Worker, "__call__", call)


def _stopped_partway(
    directory: Path,
    samples: tuple[Sample, ...],
    recipe: GridCacheRecipe,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    CountedWorker(stop_before=STOPPED_AFTER).install(monkeypatch)
    with pytest.raises(_BrokenWorker):
        build_grid_cache(
            directory,
            samples=samples,
            audio=SampleAudio.of_files(directory.parents[2], ()),
            recipe=recipe,
            worker_count=0,
        )


def test_a_rebuild_stopped_partway_leaves_the_previous_cache_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "cache" / "grids" / "descriptor"
    samples = _samples(tmp_path, 3)
    build_grid_cache(
        directory, samples=samples[:2], audio=SampleAudio.of_files(tmp_path, ()), recipe=_recipe(), worker_count=0
    )

    def fail(self: object, job: object) -> None:
        raise _BrokenWorker("stopped partway")

    monkeypatch.setattr(descriptor_cache._Worker, "__call__", fail)
    with pytest.raises(_BrokenWorker):
        build_grid_cache(
            directory, samples=samples, audio=SampleAudio.of_files(tmp_path, ()), recipe=_recipe(), worker_count=0
        )

    assert open_grid_cache(directory).hashes == tuple(sample.hash for sample in samples[:2])


def test_a_finished_rebuild_takes_the_name_and_leaves_nothing_beside_it(tmp_path: Path) -> None:
    directory = tmp_path / "cache" / "grids" / "descriptor"
    samples = _samples(tmp_path, 3)
    build_grid_cache(
        directory, samples=samples[:2], audio=SampleAudio.of_files(tmp_path, ()), recipe=_recipe(), worker_count=0
    )

    rebuilt = build_grid_cache(
        directory, samples=samples, audio=SampleAudio.of_files(tmp_path, ()), recipe=_recipe(), worker_count=0
    )

    assert rebuilt.sample_count == 3
    assert sorted(path.name for path in directory.parent.iterdir()) == ["descriptor"]


def test_a_cache_whose_files_disagree_is_refused(tmp_path: Path) -> None:
    cache = write_grid_cache(tmp_path / "cache", sample_count=4)
    (cache.directory / HASHES_FILE_NAME).write_text("\n".join(cache.hashes[:3]), encoding="utf-8")

    with pytest.raises(ValueError, match="incomplete"):
        open_grid_cache(cache.directory)


def test_a_reader_notices_a_cache_rebuilt_under_it(tmp_path: Path) -> None:
    source = GridSource.of(write_grid_cache(tmp_path / "cache", sample_count=4))
    write_grid_cache(tmp_path / "cache", sample_count=6)

    with pytest.raises(ValueError, match="rebuilt while this run read it"):
        MappedGrids(source).array()


def test_a_build_stopped_partway_continues_where_it_stopped_and_ends_as_one_pass_would(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    samples = _samples(tmp_path, SAMPLE_COUNT)
    audio = SampleAudio.of_files(tmp_path, ())
    straight = build_grid_cache(
        tmp_path / "cache" / "grids" / "straight", samples=samples, audio=audio, recipe=_recipe(), worker_count=0
    )
    directory = tmp_path / "cache" / "grids" / "descriptor"
    _stopped_partway(directory, samples, _recipe(), monkeypatch)
    continued = CountedWorker(stop_before=None)
    continued.install(monkeypatch)

    cache = build_grid_cache(directory, samples=samples, audio=audio, recipe=_recipe(), worker_count=0)

    assert continued.canonicalized == [sample.hash for sample in samples[STOPPED_AFTER:]]
    assert cache.hashes == straight.hashes
    np.testing.assert_array_equal(cache.grids, straight.grids)
    np.testing.assert_array_equal(cache.durations, straight.durations)
    assert sorted(path.name for path in directory.parent.iterdir()) == ["descriptor", "straight"]


@pytest.mark.parametrize("change", ["another recipe", "other samples"])
def test_a_build_of_another_cache_starts_over_from_the_first_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    samples = _samples(tmp_path, SAMPLE_COUNT)
    directory = tmp_path / "cache" / "grids" / "descriptor"
    _stopped_partway(directory, samples[:-1] if change == "other samples" else samples, _recipe(), monkeypatch)
    continued = CountedWorker(stop_before=None)
    continued.install(monkeypatch)

    build_grid_cache(
        directory,
        samples=samples,
        audio=SampleAudio.of_files(tmp_path, ()),
        recipe=_recipe(random_seed=1) if change == "another recipe" else _recipe(),
        worker_count=0,
    )

    assert continued.canonicalized == [sample.hash for sample in samples]
