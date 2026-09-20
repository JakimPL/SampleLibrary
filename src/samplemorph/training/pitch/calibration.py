from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.coordinates.pitch_head.store import StoredPitchHead, calibrated
from samplemorph.coordinates.readers import SubharmonicReader, subharmonic_reader
from samplemorph.geometry import REFERENCE_FREQUENCY_HZ, SEMITONES_PER_OCTAVE, semitones_from_reference
from samplemorph.tones import HarmonicTone, harmonic_tone
from samplemorph.training.frame_cache import STORED_READING, FrameCache

CALIBRATION_TONE_COUNT: Final[int] = 24
CALIBRATION_TILT_DB_PER_OCTAVE: Final[float] = -6.0
NO_RESONANCE_DB: Final[float] = 0.0
REGISTER_SHARE: Final[float] = 5.0
# Under a semitone of headroom at either end keeps every calibration tone inside the register read.
REGISTER_MARGIN_SEMITONES: Final[float] = 1.0


@dataclass(frozen=True)
class Register:
    """The span of pitches the library's own samples sound at, in semitones from the reference frequency."""

    lowest_semitones: float
    highest_semitones: float

    def fundamentals_hz(self, *, count: int) -> NDArray[np.float64]:
        """`count` fundamentals spread evenly in octaves across the register."""
        semitones = np.linspace(
            self.lowest_semitones + REGISTER_MARGIN_SEMITONES, self.highest_semitones - REGISTER_MARGIN_SEMITONES, count
        )
        return REFERENCE_FREQUENCY_HZ * 2.0 ** (semitones / SEMITONES_PER_OCTAVE)


def measured_register(cache: FrameCache, *, positions: NDArray[np.intp], reader: SubharmonicReader) -> Register:
    """Where the cached samples sound, read by the classical reader over the frames the cache already holds.

    The calibration tones are drawn across this span rather than a fixed one, so a head is
    calibrated where the library it was taught on actually sounds.
    """
    readings = [
        reader.read_frames(
            cache.frames[position, STORED_READING, : int(cache.counts[position, STORED_READING])].astype(np.float32)
        )
        for position in positions
        if cache.counts[position, STORED_READING] > 0
    ]
    semitones = np.array([reading.semitones for reading in readings])
    return Register(
        lowest_semitones=float(np.percentile(semitones, REGISTER_SHARE)),
        highest_semitones=float(np.percentile(semitones, 100.0 - REGISTER_SHARE)),
    )


def calibration_semitones(head: StoredPitchHead, *, register: Register, count: int = CALIBRATION_TONE_COUNT) -> float:
    """Where the head's lowest output bin sounds, read from plain harmonic tones whose pitch is known.

    Nothing in the training says which pitch an output bin stands for, only that a move of the input
    moves the answer with it, so one offset over the whole axis is what is left to measure. Plain
    tones are the family every other one is a coloring of, and the median over them holds where one
    tone reads oddly.
    """
    errors = []
    for fundamental_hz in register.fundamentals_hz(count=count):
        tone = HarmonicTone(
            fundamental_hz=float(fundamental_hz),
            resonance_hz=float(fundamental_hz),
            tilt_db_per_octave=CALIBRATION_TILT_DB_PER_OCTAVE,
            resonance_gain_db=NO_RESONANCE_DB,
        )
        reading = head.read(prepare_mono(harmonic_tone(tone, rate_hz=float(NOMINAL_WAV_RATE))))
        if reading is not None:
            errors.append(semitones_from_reference(float(fundamental_hz)) - reading.semitones)
    return head.description.calibration_semitones + float(np.median(errors))


def calibrate(head: StoredPitchHead, *, cache: FrameCache, positions: NDArray[np.intp]) -> StoredPitchHead:
    """The head reading in semitones from the reference frequency, its offset read over the library's own register."""
    register = measured_register(cache, positions=positions, reader=subharmonic_reader())
    return calibrated(head, semitones=calibration_semitones(head, register=register))
