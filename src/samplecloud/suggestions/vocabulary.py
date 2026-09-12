from __future__ import annotations

from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.labeling.labels import format_path, written_paths
from samplecore.labeling.vocabulary import read_vocabulary

INSTRUMENTS_CHOICE: Final[str] = "instruments"
HAND_LABELS_CHOICE: Final[str] = "hand-labels"
PROMPT_TEMPLATE: Final[str] = "This is the sound of {}."
HAND_LABEL_DEPTH: Final[int] = 2

# The instruments a tracker sample most often is, in the hand-label grammar so an accepted
# suggestion is already a label: drums first, then what is pitched or textured.
INSTRUMENT_VOCABULARY: Final[tuple[str, ...]] = (
    "BASS DRUM",
    "SNARE",
    "HI-HAT: CLOSED",
    "HI-HAT: OPEN",
    "CLAP",
    "CYMBAL: CRASH",
    "CYMBAL: RIDE",
    "TOM",
    "PERCUSSION: SHAKER",
    "PERCUSSION: COWBELL",
    "PERCUSSION: CONGA",
    "BASS: ELECTRIC",
    "BASS: SYNTH",
    "BASS: SLAP",
    "PIANO",
    "ELECTRIC PIANO",
    "ORGAN",
    "GUITAR: ACOUSTIC",
    "GUITAR: ELECTRIC",
    "STRINGS",
    "BRASS",
    "FLUTE",
    "SAXOPHONE",
    "BELL",
    "MARIMBA",
    "SYNTH: LEAD",
    "SYNTH: PAD",
    "SYNTH: PULSE",
    "CHORD",
    "CHOIR",
    "VOCAL",
    "FX",
    "NOISE",
    "CHIPTUNE",
)


def prompt_for(label: str) -> str:
    """The sentence the text tower reads for one label.

    The label's levels are read from the most specific outward and in lower case, so a
    specification reads the way a person says it: `HI-HAT: CLOSED` becomes `closed hi-hat` and
    `BASS: SYNTH` becomes `synth bass`.
    """
    path, *_ = written_paths(label)
    return PROMPT_TEMPLATE.format(" ".join(reversed(path)).lower())


def vocabulary_from(choice: str, connection: Connection) -> tuple[str, ...]:
    """The labels a scoring ranks: the shipped instruments, the tags people wrote, or a file's lines.

    The hand-label vocabulary takes every category and every specification under one, as they
    are written; a file names one label per line in the same grammar.

    Raises:
        ValueError: the choice names a file that holds no label.
    """
    match choice:
        case _ if choice == INSTRUMENTS_CHOICE:
            return INSTRUMENT_VOCABULARY
        case _ if choice == HAND_LABELS_CHOICE:
            usages = read_vocabulary(connection).usages
            return tuple(format_path(usage.path) for usage in usages if usage.depth <= HAND_LABEL_DEPTH)
        case _:
            labels = tuple(line.strip() for line in Path(choice).read_text(encoding="utf-8").splitlines())
            named = tuple(label for label in labels if label)
            if not named:
                raise ValueError(f"the vocabulary file {choice} holds no label")
            return named
