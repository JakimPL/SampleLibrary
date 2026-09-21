from __future__ import annotations

from typing import Protocol

from sampledescriptor.geometry import GridGeometry
from sampledescriptor.images import SoundImage
from samplemorph.canonicalizers.common import PreparedMono


class Canonicalizer(Protocol):
    """Turns a stored waveform into the fixed-size sound image a descriptor reads.

    An implementation returns the same grid shape for every waveform however long or loud it was,
    so any two samples' images are directly comparable. The frequency axis is logarithmic, which
    turns a change of playback rate into a translation along it; the translation is measured,
    moved out of the grid, and carried as a conditioner, so the grid describes timbre and the
    conditioners describe the reading it was heard at.

    `canonicalize` reads frames already prepared by `prepare_mono`, which is where the pipeline takes
    audio in.
    """

    @property
    def geometry(self) -> GridGeometry: ...

    def canonicalize(self, mono: PreparedMono) -> SoundImage: ...
