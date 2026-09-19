from __future__ import annotations

from typing import Protocol

from samplemorph.canonicalizers.common import PreparedMono


class ReadPitch(Protocol):
    """A pitch in semitones from the reference frequency in the nominal frame, and how far its reader trusts it, in ``[0, 1]``."""

    @property
    def semitones(self) -> float: ...

    @property
    def reliability(self) -> float: ...


class PitchReader(Protocol):
    """Anything that reads a sound's pitch under a name: a classical estimator or a trained head.

    A reader returns None for a sound it finds no pitch in at all.
    """

    @property
    def name(self) -> str: ...

    def read(self, mono: PreparedMono) -> ReadPitch | None: ...
