from __future__ import annotations

from collections.abc import Iterable
from typing import Final, Self

from pydantic import BaseModel

from samplecore.models.base import FROZEN

TAG_SEPARATOR: Final[str] = ","
LEVEL_SEPARATOR: Final[str] = ":"
DISPLAY_LEVEL_SEPARATOR: Final[str] = ": "
DISPLAY_TAG_SEPARATOR: Final[str] = ", "

LabelPath = tuple[str, ...]


def written_paths(text: str) -> tuple[LabelPath, ...]:
    """The tag paths a label names, in the order the person wrote them.

    The order is the one reading of a label the set of its tags loses: a person writes the tag they
    think of first ahead of the qualifiers, so a reader that can show one tag per sample shows the
    first. A path written twice is kept once, at its first position.
    """
    paths: list[LabelPath] = []
    for tag in text.upper().split(TAG_SEPARATOR):
        levels = tuple(level.strip() for level in tag.split(LEVEL_SEPARATOR))
        path = tuple(level for level in levels if level)
        if path and path not in paths:
            paths.append(path)
    return tuple(paths)


def canonical_label(text: str) -> str:
    """A label in the one spelling it is stored and compared in: ``HI-HAT: CLOSED, LO-FI``.

    Case, the spacing around separators and a tag written twice all follow how a person happened to
    type, and none of them changes what the label says, so every wording of one label is stored as
    that one label. The tags keep the order they were written in.

    Raises:
        ValueError: the text names no tag.
    """
    paths = written_paths(text)
    if not paths:
        raise ValueError(f"a label names at least one tag, as in 'HI-HAT: CLOSED'; got {text!r}")
    return DISPLAY_TAG_SEPARATOR.join(format_path(path) for path in paths)


def first_use_ranks(labels_in_time_order: Iterable[str]) -> dict[LabelPath, int]:
    """Every tag's rank by the moment a person first used it, the tags above it included.

    A rank is what a reader hangs something lasting on, such as a color: a tag used for the first
    time takes the rank after the last. Two tags first used in one label rank in the order they were
    written.
    """
    first_uses: dict[LabelPath, None] = {}
    for label in labels_in_time_order:
        for path in written_paths(label):
            for depth in range(1, len(path) + 1):
                first_uses.setdefault(path[:depth], None)
    return {path: rank for rank, path in enumerate(first_uses)}


class SampleLabel(BaseModel):
    """What a label says about a sample: the set of tag paths it names.

    A person writes ``HI-HAT: CLOSED, LO-FI`` -- tags separated by commas, each one a path whose
    colons step from a broad top level down to a specification that only means something under it.
    The whole path is a tag's identity, so ``ELECTRIC`` under ``BASS`` and ``ELECTRIC`` under
    ``GUITAR`` are two different tags, and a path asserts every tag above it: a closed hi-hat
    is also a hi-hat. Tags are attributes a sample carries side by side, which is what lets one
    sample be both a snare and lo-fi.
    """

    model_config = FROZEN

    paths: frozenset[LabelPath]

    @classmethod
    def parse(cls, text: str) -> Self:
        """Read a label as a person typed it, in the upper case labels are stored in."""
        return cls(paths=frozenset(written_paths(text)))

    @property
    def closure(self) -> frozenset[LabelPath]:
        """Every tag the label asserts, including each tag above a specification."""
        return frozenset(path[:depth] for path in self.paths for depth in range(1, len(path) + 1))

    @property
    def top_level(self) -> frozenset[str]:
        """The top levels alone, which is the level-zero reading of the label."""
        return frozenset(path[0] for path in self.paths)

    def truncated(self, *, depth: int) -> SampleLabel:
        """The label read to at most `depth` levels, so a metric can be taken at a chosen coarseness.

        Raises:
            ValueError: `depth` is below one, which would leave nothing of any tag.
        """
        if depth < 1:
            raise ValueError(f"a label keeps at least one level of each tag, got depth {depth}")
        return SampleLabel(paths=frozenset(path[:depth] for path in self.paths))


def label_agreement(first: SampleLabel, second: SampleLabel) -> float:
    """How much two labels say the same thing, from 0 for nothing shared to 1 for the same label.

    The Jaccard overlap of the two closures gives graded credit along the hierarchy: two closed
    hi-hats agree fully, a closed and an open hi-hat agree on being hi-hats, and a synth pluck and a
    chiptune pulse synth agree on being synths. A specification only ever adds partial credit, so a
    deeper label refines an agreement instead of contradicting it.
    """
    union = first.closure | second.closure
    if not union:
        return 0.0
    return len(first.closure & second.closure) / len(union)


def format_path(path: LabelPath) -> str:
    """A tag path written back the way a person writes it."""
    return DISPLAY_LEVEL_SEPARATOR.join(path)
