from __future__ import annotations

from pathlib import Path
from typing import Final

from sqlalchemy import Connection

from samplecore.labeling.labels import format_path, written_paths
from samplecore.labeling.vocabulary import read_vocabulary

INSTRUMENTS_CHOICE: Final[str] = "instruments"
HAND_LABELS_CHOICE: Final[str] = "hand-labels"
PROMPT_TEMPLATE: Final[str] = "This is the sound of {}."
COMMENT_PREFIX: Final[str] = "#"
HAND_LABEL_DEPTH: Final[int] = 2

# The instruments a tracker sample most often is, in the hand-label grammar so an accepted
# category is already a label: drums first, then what is pitched or textured.
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


class VocabularyRefused(ValueError):
    """Raised when a vocabulary file cannot be read as a list of labels."""


def vocabulary_from(choice: str, connection: Connection) -> tuple[str, ...]:
    """The labels a scoring ranks: the shipped instruments, the tags people wrote, or a file's lines.

    The hand-label vocabulary takes every category and every specification under one, as they
    are written; a file names one label per line in the same grammar (see `read_vocabulary_file`).

    Raises:
        VocabularyRefused: the choice names a file that cannot be read, or one holding no label.
    """
    match choice:
        case _ if choice == INSTRUMENTS_CHOICE:
            return INSTRUMENT_VOCABULARY
        case _ if choice == HAND_LABELS_CHOICE:
            usages = read_vocabulary(connection).usages
            return tuple(format_path(usage.path) for usage in usages if usage.depth <= HAND_LABEL_DEPTH)
        case _:
            return read_vocabulary_file(Path(choice))


def read_vocabulary_file(path: Path) -> tuple[str, ...]:
    """The labels a vocabulary file names, one tag path per line, each once, in the order first written.

    Blank lines and lines starting with `#` are passed over, and every label is read in its
    canonical spelling, so `hi-hat:closed` and `HI-HAT: CLOSED` name one label.

    Raises:
        VocabularyRefused: the file cannot be read, a line names more than one tag, or no label remains.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise VocabularyRefused(f"the vocabulary file {path} cannot be read ({error})") from error

    labels: dict[str, None] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        written = line.strip()
        if not written or written.startswith(COMMENT_PREFIX):
            continue
        paths = written_paths(written)
        if len(paths) != 1:
            raise VocabularyRefused(
                f"line {line_number} of {path} names {len(paths)} tags; each line names one, as in 'HI-HAT: CLOSED'"
            )
        labels[format_path(paths[0])] = None
    if not labels:
        raise VocabularyRefused(f"the vocabulary file {path} holds no label")
    return tuple(labels)
