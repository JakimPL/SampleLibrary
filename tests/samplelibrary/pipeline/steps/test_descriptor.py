from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from sampledescriptor import pretrained
from sampledescriptor.geometry import Anchor
from sampledescriptor.pretrained import PretrainedGrid, PretrainedRelease, write_pretrained_release
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.layout import PipelineLayout
from samplelibrary.pipeline.results import StepAction
from samplelibrary.pipeline.settings import DescriptorSource, PipelineSettings
from samplelibrary.pipeline.steps.descriptor import DESCRIPTOR, GRID_CACHE, PRETRAINED_INPUT
from samplelibrary.pipeline.steps.kinds import StepRefused
from samplelibrary.pipeline.steps.library import library_graph

PUBLISHED: Final[PretrainedRelease] = PretrainedRelease(
    url="https://example.com/descriptor.pt",
    sha256="ab" * 32,
    grid=PretrainedGrid(canonicalizer="log_frequency", anchor=Anchor.NONE, bands_per_semitone=3),
)


@pytest.fixture
def context(tmp_path: Path, connection: Connection) -> PipelineContext:
    library_root = tmp_path / "library"
    return PipelineContext(
        config=LibraryConfig(library_root=library_root),
        settings=PipelineSettings(descriptor_source=DescriptorSource.PRETRAINED),
        connection=connection,
        layout=PipelineLayout(library_root=library_root),
    )


@pytest.fixture(name="published")
def fixture_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PretrainedRelease:
    """The installation's release record: the pipeline plans from it alone, before any download."""
    path = tmp_path / "pretrained.toml"
    write_pretrained_release(PUBLISHED, path)
    monkeypatch.setattr(pretrained, "PRETRAINED_RELEASE_PATH", path)
    return PUBLISHED


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


def test_a_version_without_a_published_descriptor_refuses_the_step(
    context: PipelineContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pretrained, "PRETRAINED_RELEASE_PATH", tmp_path / "missing.toml")

    with pytest.raises(StepRefused, match="release-descriptor"):
        library_graph(DescriptorSource.PRETRAINED).step(DESCRIPTOR).evaluate(context)
