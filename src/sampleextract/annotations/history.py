from __future__ import annotations

from samplecore.models.annotation import AnnotationDecisions
from samplecore.storage.repositories.annotation_history import AnnotationChange

MOMENT_FORMAT = "%Y-%m-%d %H:%M:%S"
NOTHING = "nothing"


def history_lines(changes: tuple[AnnotationChange, ...]) -> tuple[str, ...]:
    """One line per entry of the label history, in the local time `annotations restore --at` reads back."""
    return tuple(
        f"{change.recorded_at.astimezone():{MOMENT_FORMAT}}  {change.operation.value:<8}  {change.sample_hash}  "
        f"{_describe(change.previous)} -> {_describe(change.current)}  ({change.role})"
        for change in changes
    )


def _describe(decisions: AnnotationDecisions | None) -> str:
    """What one side of a change held, in the words a person would recognize the sample by."""
    if decisions is None:
        return NOTHING
    parts = []
    if decisions.label is not None:
        parts.append(repr(decisions.label))
    if decisions.rating is not None:
        parts.append(f"rated {decisions.rating}")
    if decisions.favorite:
        parts.append("favorite")
    return ", ".join(parts) or NOTHING
