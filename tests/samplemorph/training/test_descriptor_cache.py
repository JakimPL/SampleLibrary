from __future__ import annotations

from pathlib import Path

import pytest
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.geometry import Anchor
from samplemorph.training import descriptor_cache
from samplemorph.training.descriptor_cache import (
    HASHES_FILE_NAME,
    GridCacheRecipe,
    GridSource,
    MappedGrids,
    build_grid_cache,
    open_grid_cache,
)
from tests.samplemorph.conftest import harmonic_tone
from tests.samplemorph.training.conftest import write_grid_cache

FRAME_COUNT = 8192


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


def _recipe() -> GridCacheRecipe:
    return GridCacheRecipe(
        canonicalizer_name="log_frequency",
        anchor=Anchor.NONE,
        bands_per_semitone=1,
        view_count=1,
        view_range_semitones=2.0,
        random_seed=0,
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
