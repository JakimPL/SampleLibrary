from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self

from sqlalchemy import Connection

from samplecore.labeling.labels import LabelPath, SampleLabel, written_paths
from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository


@dataclass(frozen=True)
class TagUsage:
    """One tag and how many samples carry it, counting every sample labeled with a specification of it."""

    path: LabelPath
    sample_count: int

    @property
    def depth(self) -> int:
        return len(self.path)


@dataclass(frozen=True)
class LabelVocabulary:
    """The tags a person has used so far, as a tree with a count at every node.

    A count includes the samples labeled with any specification below the tag, so ``HI-HAT`` counts
    its closed and open hi-hats too and a reader sees how much support a category has at each level.
    The two findings below surface where the wording drifted, for the person to settle in the
    interface: this class reads the labels and changes nothing.
    """

    usages: tuple[TagUsage, ...]

    @classmethod
    def from_labels(cls, labels: Iterable[SampleLabel]) -> Self:
        counts: Counter[LabelPath] = Counter()
        for label in labels:
            counts.update(label.closure)
        usages = tuple(
            TagUsage(path=path, sample_count=count)
            for path, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        )
        return cls(usages=usages)

    @property
    def top_level(self) -> tuple[TagUsage, ...]:
        """The broad categories, most used first."""
        return tuple(usage for usage in self.usages if usage.depth == 1)

    def children(self, path: LabelPath) -> tuple[TagUsage, ...]:
        """The specifications written directly under one tag, most used first."""
        return tuple(usage for usage in self.usages if usage.depth == len(path) + 1 and usage.path[:-1] == path)

    @property
    def names_used_at_two_depths(self) -> tuple[str, ...]:
        """Names that stand as a category of their own and also as a specification under another.

        ``ELECTRIC`` on its own beside ``BASS: ELECTRIC`` is usually a comma typed for a colon;
        ``SYNTH`` beside ``BASS: SYNTH`` may be meant both ways. Either way the person deciding wants
        to see it.
        """
        roots = {usage.path[0] for usage in self.top_level}
        deeper = {usage.path[-1] for usage in self.usages if usage.depth > 1}
        return tuple(sorted(roots & deeper))

    @property
    def singletons(self) -> tuple[LabelPath, ...]:
        """Tags carried by exactly one sample, which no metric can yet read anything from."""
        return tuple(usage.path for usage in self.usages if usage.sample_count == 1)


def first_use_ranks(annotations: Iterable[SampleAnnotation]) -> dict[LabelPath, int]:
    """Every tag's rank by the moment a person first used it, the categories above a tag included.

    A rank is what a reader hangs something lasting on, such as a color: it stays with a tag as the
    vocabulary grows, and a tag used for the first time takes the rank after the last. Two tags first
    used in one annotation rank in the order they were written.
    """
    first_uses: dict[LabelPath, None] = {}
    for annotation in sorted(annotations, key=lambda candidate: candidate.annotated_at):
        if annotation.label is None:
            continue
        for path in written_paths(annotation.label):
            for depth in range(1, len(path) + 1):
                first_uses.setdefault(path[:depth], None)
    return {path: rank for rank, path in enumerate(first_uses)}


def read_vocabulary(connection: Connection) -> LabelVocabulary:
    """The tags in use across every annotation carrying a label, read and never written back."""
    annotations = PostgresSampleAnnotationRepository(connection).list_all()
    return LabelVocabulary.from_labels(
        SampleLabel.parse(annotation.label) for annotation in annotations if annotation.label is not None
    )
