from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self

from sqlalchemy import Connection

from samplecore.labeling.labels import LabelPath, SampleLabel
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
    its closed and open hi-hats too and a reader sees how much support a tag has at each level.
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
        """The top levels, most used first."""
        return tuple(usage for usage in self.usages if usage.depth == 1)

    def children(self, path: LabelPath) -> tuple[TagUsage, ...]:
        """The specifications written directly under one tag, most used first."""
        return tuple(usage for usage in self.usages if usage.depth == len(path) + 1 and usage.path[:-1] == path)

    @property
    def names_used_at_two_depths(self) -> tuple[str, ...]:
        """Names that stand as a top level of their own and also as a specification under another.

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


def read_vocabulary(connection: Connection) -> LabelVocabulary:
    """The tags in use across every annotation carrying a label, read and never written back."""
    annotations = PostgresSampleAnnotationRepository(connection).list_all()
    return LabelVocabulary.from_labels(
        SampleLabel.parse(annotation.label) for annotation in annotations if annotation.label is not None
    )
