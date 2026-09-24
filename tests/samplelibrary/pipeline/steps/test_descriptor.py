from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.hashing import file_sha256
from sampledescriptor import pretrained
from sampledescriptor.geometry import Anchor
from sampledescriptor.pretrained import PRETRAINED_MANIFEST_NAME, PRETRAINED_MODEL_NAME, PretrainedManifest
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.layout import PipelineLayout
from samplelibrary.pipeline.results import StepAction
from samplelibrary.pipeline.settings import DescriptorSource, PipelineSettings
from samplelibrary.pipeline.steps.descriptor import DESCRIPTOR, GRID_CACHE, PRETRAINED_INPUT
from samplelibrary.pipeline.steps.kinds import StepRefused
from samplelibrary.pipeline.steps.library import library_graph

BUNDLED_MANIFEST: Final[PretrainedManifest] = PretrainedManifest(
    canonicalizer="log_frequency", anchor=Anchor.NONE, bands_per_semitone=3
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


@pytest.fixture
def bundled_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An installation's bundle: the pipeline reads the manifest and the model's bytes, never the network."""
    directory = tmp_path / "bundle"
    directory.mkdir()
    (directory / PRETRAINED_MODEL_NAME).write_bytes(b"weights")
    (directory / PRETRAINED_MANIFEST_NAME).write_text(BUNDLED_MANIFEST.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(pretrained, "PRETRAINED_DIRECTORY", directory)
    return directory / PRETRAINED_MODEL_NAME


def test_the_bundled_descriptor_is_adopted_sealed_and_then_left_as_it_stands(
    context: PipelineContext, bundled_model: Path
) -> None:
    step = library_graph(DescriptorSource.PRETRAINED).step(DESCRIPTOR)

    adopting = step.evaluate(context)
    assert adopting.action is StepAction.RUN
    assert adopting.inputs == {PRETRAINED_INPUT: file_sha256(bundled_model)}
    assert adopting.argv[:2] == ("descriptor", "adopt")

    adopted = context.config.library_root / "models" / "descriptors" / f"{adopting.argv[-1]}.pt"
    adopted.parent.mkdir(parents=True)
    adopted.write_bytes(bundled_model.read_bytes())
    sealing = step.evaluate(context)
    assert sealing.action is StepAction.SEAL
    step.seal(context, sealing)

    assert step.evaluate(context).action is StepAction.SKIP


def test_the_grid_cache_is_read_on_the_bundled_descriptors_axis_without_retuned_views(
    context: PipelineContext, bundled_model: Path  # pylint: disable=unused-argument
) -> None:
    plan = library_graph(DescriptorSource.PRETRAINED).step(GRID_CACHE).evaluate(context)

    flags = dict(zip(plan.argv[::2], plan.argv[1::2], strict=False))
    assert flags["--canonicalizer"] == BUNDLED_MANIFEST.canonicalizer
    assert flags["--bands-per-semitone"] == str(BUNDLED_MANIFEST.bands_per_semitone)
    assert flags["--views"] == "0"


def test_an_installation_without_a_bundled_descriptor_refuses_the_step(
    context: PipelineContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pretrained, "PRETRAINED_DIRECTORY", tmp_path / "no-bundle")

    with pytest.raises(StepRefused, match="bundle-descriptor"):
        library_graph(DescriptorSource.PRETRAINED).step(DESCRIPTOR).evaluate(context)
