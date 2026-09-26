from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.storage.staging import partial_path
from sampledescriptor.pretrained import MISSING_RELEASE_MESSAGE, PretrainedRelease
from sampledescriptor.training.descriptor.cache import grid_cache_directory
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.layout import PipelineLayout
from samplelibrary.pipeline.results import StepAction
from samplelibrary.pipeline.scratch import remove_pipeline_outputs
from samplelibrary.pipeline.settings import DescriptorSource, PipelineSettings
from samplelibrary.pipeline.steps.descriptor import DESCRIPTOR, GRID_CACHE, PRETRAINED_INPUT
from samplelibrary.pipeline.steps.kinds import StepRefused
from samplelibrary.pipeline.steps.library import library_graph


@pytest.fixture
def context(tmp_path: Path, connection: Connection) -> PipelineContext:
    library_root = tmp_path / "library"
    return PipelineContext(
        config=LibraryConfig(library_root=library_root),
        settings=PipelineSettings(descriptor_source=DescriptorSource.PRETRAINED),
        connection=connection,
        layout=PipelineLayout(library_root=library_root),
    )


def test_the_pretrained_descriptor_is_adopted_sealed_and_then_left_as_it_stands(
    context: PipelineContext, published: PretrainedRelease
) -> None:
    step = library_graph(DescriptorSource.PRETRAINED).step(DESCRIPTOR)

    adopting = step.evaluate(context)
    assert adopting.action is StepAction.RUN
    assert adopting.inputs == {PRETRAINED_INPUT: published.sha256}
    assert adopting.argv[:2] == ("descriptor", "adopt")

    adopted = context.config.library_root / "models" / "descriptors" / f"{adopting.argv[-1]}.pt"
    adopted.parent.mkdir(parents=True)
    adopted.write_bytes(b"weights")
    sealing = step.evaluate(context)
    assert sealing.action is StepAction.SEAL
    step.seal(context, sealing)

    assert step.evaluate(context).action is StepAction.SKIP


def test_the_grid_cache_is_read_on_the_pretrained_descriptors_axis_without_retuned_views(
    context: PipelineContext, published: PretrainedRelease
) -> None:
    plan = library_graph(DescriptorSource.PRETRAINED).step(GRID_CACHE).evaluate(context)

    flags = dict(zip(plan.argv[::2], plan.argv[1::2], strict=False))
    assert flags["--canonicalizer"] == published.grid.canonicalizer
    assert flags["--bands-per-semitone"] == str(published.grid.bands_per_semitone)
    assert flags["--views"] == "0"


@pytest.mark.usefixtures("unpublished")
def test_a_version_without_a_published_descriptor_refuses_the_step(context: PipelineContext) -> None:
    with pytest.raises(StepRefused, match=MISSING_RELEASE_MESSAGE):
        library_graph(DescriptorSource.PRETRAINED).step(DESCRIPTOR).evaluate(context)


def _cache_name(context: PipelineContext) -> str:
    argv = library_graph(DescriptorSource.PRETRAINED).step(GRID_CACHE).evaluate(context).argv
    return argv[argv.index("--cache") + 1]


def _left_partway(context: PipelineContext, name: str) -> Path:
    partial = partial_path(grid_cache_directory(context.config.library_root, name=name))
    partial.mkdir(parents=True)
    (partial / "grids.npy").write_bytes(b"rows")
    return partial


@pytest.mark.usefixtures("published")
def test_a_grid_cache_for_new_inputs_clears_what_older_inputs_left_partway(context: PipelineContext) -> None:
    step = library_graph(DescriptorSource.PRETRAINED).step(GRID_CACHE)
    current = partial_path(grid_cache_directory(context.config.library_root, name=_cache_name(context)))
    older = _left_partway(context, "descriptor-0123456789abcdef")
    current.mkdir(parents=True)

    plan = step.evaluate(context)

    assert plan.action is StepAction.RUN
    assert plan.discard == (older,)


@pytest.mark.usefixtures("published")
def test_redoing_a_grid_cache_clears_its_own_build_left_partway(context: PipelineContext) -> None:
    step = library_graph(DescriptorSource.PRETRAINED).step(GRID_CACHE)
    current = _left_partway(context, _cache_name(context))

    removed = step.forget(context)

    assert current in removed
    assert not current.exists()


def test_starting_over_clears_every_grid_cache_left_partway(context: PipelineContext) -> None:
    partials = (
        _left_partway(context, "descriptor-0123456789abcdef"),
        _left_partway(context, "descriptor-fedcba9876543210"),
    )

    removed = remove_pipeline_outputs(context.layout, library_graph(DescriptorSource.PRETRAINED).owned_outputs)

    assert set(partials) <= set(removed)
    assert not any(partial.exists() for partial in partials)
