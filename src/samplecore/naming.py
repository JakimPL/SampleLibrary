from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import Final

_SANITIZED_NAME_PATTERN: Final = re.compile(r"[^a-z0-9 _-]")
_WHITESPACE_PATTERN: Final = re.compile(r"\s+")


def sanitize_sample_name(name: str) -> str:
    """Fold an occurrence's raw name to a display-safe form: lowercase, `[a-z0-9 _-]` only.

    Runs of stripped-out characters collapse rather than leaving gaps, and the result is
    trimmed of leading/trailing whitespace.
    """
    lowered = name.strip().lower()
    stripped = _SANITIZED_NAME_PATTERN.sub("", lowered)
    return _WHITESPACE_PATTERN.sub(" ", stripped).strip()


def choose_dominant_name(names: Iterable[str]) -> str:
    """Resolve one display name out of a sample's, possibly conflicting, occurrence names.

    Sanitizes every name and picks the most frequent sanitized form. A tie is broken by
    ascending alphabetical order -- a stable, deterministic rule that favours neither the
    shortest nor the longest candidate. An input with no non-empty sanitized name (a sample
    with no occurrences, or occurrences named only with stripped characters) resolves to `""`.
    """
    sanitized_names = [sanitize_sample_name(name) for name in names]
    non_empty_names = [name for name in sanitized_names if name != ""]
    if not non_empty_names:
        return ""

    counts = Counter(non_empty_names)
    highest_count = max(counts.values())
    candidates = sorted(name for name, count in counts.items() if count == highest_count)
    return candidates[0]
