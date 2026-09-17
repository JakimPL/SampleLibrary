from __future__ import annotations

from typing import Final

from samplecore.labeling.labels import format_path
from samplecore.labeling.vocabulary import LabelVocabulary, TagUsage

INDENT: Final[str] = "    "


def vocabulary_lines(vocabulary: LabelVocabulary) -> tuple[str, ...]:
    """The vocabulary as an indented tree, most-used top levels first, with what a person may want to settle."""
    lines: list[str] = []
    for usage in vocabulary.top_level:
        lines.extend(_subtree_lines(vocabulary, usage, depth=0))
    if vocabulary.names_used_at_two_depths:
        names = ", ".join(vocabulary.names_used_at_two_depths)
        lines.append(f"Used both as a top level and as a specification under another: {names}.")
    if vocabulary.singletons:
        paths = ", ".join(format_path(path) for path in vocabulary.singletons)
        lines.append(f"Carried by one sample each: {paths}.")
    return tuple(lines)


def _subtree_lines(vocabulary: LabelVocabulary, usage: TagUsage, *, depth: int) -> list[str]:
    lines = [f"{INDENT * depth}{usage.sample_count:5d}  {usage.path[-1]}"]
    for child in vocabulary.children(usage.path):
        lines.extend(_subtree_lines(vocabulary, child, depth=depth + 1))
    return lines
