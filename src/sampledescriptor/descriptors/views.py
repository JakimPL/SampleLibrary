from __future__ import annotations

from samplecore.waveform import resample_by_semitones
from sampledescriptor.canonicalizers import Canonicalizer
from sampledescriptor.images import SoundImage
from samplemorph.canonicalizers.common import PreparedMono


def retuned_view(mono: PreparedMono, *, semitones: float, canonicalizer: Canonicalizer) -> SoundImage:
    """The canonical image of a sound read `semitones` above the rate it was stored at.

    The waveform is resampled, as a tracker reading the same frames faster does, so the pitch and the
    length change together and the image is made from what that reading sounds like. The grid cache
    makes its retuned views this way, and so does every reading that needs a sound at a known retuning.
    """
    return canonicalizer.canonicalize(PreparedMono(resample_by_semitones(mono, semitones=semitones)))
