from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from samplecore.models.category import SampleCategory

_SEPARATOR_PATTERN: Final = re.compile(r"[ _-]")

_CATEGORY_KEYWORDS: Final[tuple[tuple[SampleCategory, tuple[str, ...]], ...]] = (
    (SampleCategory.KICK, ("kick", "bassdrum", "bd", "boom")),
    (SampleCategory.SNARE, ("snare", "rimshot", "rim")),
    (SampleCategory.CLAP, ("clap",)),
    (SampleCategory.HI_HAT, ("hihat", "hat", "hh")),
    (SampleCategory.CYMBAL, ("cymbal", "crash", "ride", "splash")),
    (
        SampleCategory.PERCUSSION,
        ("percussion", "perc", "tom", "conga", "bongo", "shaker", "tambourine", "cowbell"),
    ),
    (SampleCategory.BASS, ("bass", "sub", "808")),
    (SampleCategory.LEAD, ("lead", "arpeggio", "arp")),
    (SampleCategory.PAD, ("pad", "ambient", "atmos", "drone")),
    (SampleCategory.PLUCK, ("pluck", "stab")),
    (SampleCategory.VOCAL, ("vocal", "voice", "choir", "chant", "vox")),
    (SampleCategory.FX, ("effect", "sweep", "riser", "impact", "glitch", "fx")),
    (SampleCategory.LOOP, ("loop",)),
)


def _matching_key(name: str) -> str:
    """Fold a name to lowercase with every space, underscore, and hyphen removed.

    Lets each keyword in `_CATEGORY_KEYWORDS` be written once in its plainest joined form (e.g.
    "hihat") while still matching every real-world separator style a tracker sample name might use
    ("hi-hat", "hi_hat", "hi hat", "HiHat").
    """
    return _SEPARATOR_PATTERN.sub("", name.strip().lower())


def classify_sample_category(names: Iterable[str]) -> SampleCategory:
    """Guess a sample's instrument category from its, possibly conflicting, occurrence names.

    Checks each of a sample's occurrence names against `_CATEGORY_KEYWORDS`, in the table's own
    fixed order, and returns the first category any name matches -- checking every occurrence name
    (not just the single chosen display name) means a sample named differently across its module
    occurrences still classifies correctly if any one of them carries a recognizable keyword. The
    fixed order resolves ambiguous names deliberately: a "bassdrum" sample matches KICK before it
    ever reaches BASS's own "bass" keyword, since KICK is checked first. A sample with no occurrence
    name matching any keyword resolves to `SampleCategory.UNCATEGORIZED`. This is a plain keyword
    table, easy to retune against how well it agrees with real listening -- a first-pass heuristic,
    not a final classifier.
    """
    matching_keys = [_matching_key(name) for name in names]
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in matching_key for matching_key in matching_keys for keyword in keywords):
            return category

    return SampleCategory.UNCATEGORIZED
