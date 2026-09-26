from __future__ import annotations

import pytest

from sampledescriptor.pretrained import MISSING_RELEASE_MESSAGE
from samplelibrary.pipeline.graph import ALL_TARGET
from samplelibrary.pipeline.settings import DescriptorSource
from samplelibrary.pipeline.steps.descriptor import DESCRIPTOR, EVALUATION, MODULE_EVALUATION
from samplelibrary.pipeline.steps.library import (
    CATALOG_TARGET,
    CLOUD_TARGET,
    TRAINING_ONLY_STEPS,
    every_step_name,
    library_graph,
)
from samplelibrary.pipeline.steps.listening import TEACHER


def test_a_library_taking_the_bundled_descriptor_builds_nothing_only_training_reads() -> None:
    graph = library_graph(DescriptorSource.PRETRAINED)

    ordered = {step.name for step in graph.order((ALL_TARGET,))}

    assert not ordered & TRAINING_ONLY_STEPS
    assert graph.step(DESCRIPTOR).requires == ()
    assert {EVALUATION, MODULE_EVALUATION}.isdisjoint(graph.targets[CLOUD_TARGET])


def test_a_library_training_its_descriptor_builds_the_listening_reading_and_the_scores() -> None:
    graph = library_graph(DescriptorSource.TRAINED)

    ordered = {step.name for step in graph.order((ALL_TARGET,))}

    assert TRAINING_ONLY_STEPS <= ordered
    assert TEACHER in graph.step(DESCRIPTOR).requires


@pytest.mark.usefixtures("unpublished")
def test_a_library_naming_the_pretrained_descriptor_this_version_lacks_builds_its_catalog_alone() -> None:
    graph = library_graph(DescriptorSource.PRETRAINED)

    refusal = graph.unavailable_reason((ALL_TARGET,))

    assert refusal is not None and refusal.startswith(MISSING_RELEASE_MESSAGE)
    assert graph.unavailable_reason((CATALOG_TARGET,)) is None


@pytest.mark.usefixtures("unpublished")
def test_a_library_training_its_descriptor_needs_nothing_published() -> None:
    assert library_graph(DescriptorSource.TRAINED).unavailable_reason((ALL_TARGET,)) is None


@pytest.mark.usefixtures("published")
def test_a_version_carrying_its_descriptor_builds_everything_with_it() -> None:
    assert library_graph(DescriptorSource.PRETRAINED).unavailable_reason((ALL_TARGET,)) is None


@pytest.mark.parametrize("source", list(DescriptorSource))
def test_every_step_either_source_holds_is_one_a_step_table_may_name(source: DescriptorSource) -> None:
    assert {step.name for step in library_graph(source).steps} <= every_step_name()
