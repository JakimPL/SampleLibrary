from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.coordinates.pitch_head.network import PitchNetwork
from samplemorph.coordinates.pitch_head.shape import PitchHeadShape
from samplemorph.coordinates.pitch_head.store import PitchHeadDescription, StoredPitchHead, calibrated
from samplemorph.coordinates.readers import subharmonic_reader
from samplemorph.geometry import semitones_from_reference
from samplemorph.tones import HarmonicTone, harmonic_tone
from samplemorph.training.frame_cache import STORED_READING, FrameCache
from samplemorph.training.pitch.calibration import (
    CALIBRATION_TILT_DB_PER_OCTAVE,
    NO_RESONANCE_DB,
    Register,
    calibration_semitones,
    measured_register,
)
from tests.samplemorph.training.pitch.conftest import ANALYSIS, write_frame_cache

CHANNELS = (4, 6)
SHIFT_REACH_BINS = 12
TONE_COUNT = 4
KNOWN_OFFSET_SEMITONES = 7.0
REGISTER = Register(lowest_semitones=-24.0, highest_semitones=0.0)
EXACT = 1e-4
# A bin of the analysis is a third of a semitone, and the refinement answers between bins.
READING_TOLERANCE_SEMITONES = 1.0


def _head(*, calibration_semitones_of: float) -> StoredPitchHead:
    torch.manual_seed(0)
    shape = PitchHeadShape(
        band_count=ANALYSIS.band_count,
        bins_per_octave=ANALYSIS.bins_per_octave,
        shift_reach_bins=SHIFT_REACH_BINS,
        channels=CHANNELS,
        kernel_size=5,
    )
    description = PitchHeadDescription(
        name="under-test",
        cache="tiny",
        analysis=ANALYSIS,
        shape=shape,
        calibration_semitones=calibration_semitones_of,
        trusted_reliability=0.5,
        random_seed=0,
        epochs=1,
        trained_sample_count=8,
        best_validation_error=0.25,
        validation_hashes=(),
        parameters={},
    )
    return StoredPitchHead(network=PitchNetwork(shape), description=description, device=torch.device("cpu"))


def _plain_tone(fundamental_hz: float) -> HarmonicTone:
    return HarmonicTone(
        fundamental_hz=fundamental_hz,
        resonance_hz=fundamental_hz,
        tilt_db_per_octave=CALIBRATION_TILT_DB_PER_OCTAVE,
        resonance_gain_db=NO_RESONANCE_DB,
    )


def test_the_calibration_takes_back_out_an_offset_put_into_a_head() -> None:
    head = _head(calibration_semitones_of=0.0)
    measured = calibration_semitones(head, register=REGISTER, count=TONE_COUNT)

    off_by = calibrated(head, semitones=measured + KNOWN_OFFSET_SEMITONES)

    assert calibration_semitones(off_by, register=REGISTER, count=TONE_COUNT) == pytest.approx(measured, abs=EXACT)


def test_a_calibrated_head_reads_the_tones_it_was_calibrated_on_where_they_sound() -> None:
    head = _head(calibration_semitones_of=0.0)
    tuned = calibrated(head, semitones=calibration_semitones(head, register=REGISTER, count=TONE_COUNT))

    errors = []
    for fundamental_hz in REGISTER.fundamentals_hz(count=TONE_COUNT):
        reading = tuned.read(prepare_mono(harmonic_tone(_plain_tone(float(fundamental_hz)), rate_hz=NOMINAL_WAV_RATE)))
        assert reading is not None
        errors.append(semitones_from_reference(float(fundamental_hz)) - reading.semitones)

    assert float(np.median(errors)) == pytest.approx(0.0, abs=EXACT)


def test_the_register_spans_where_the_cache_s_own_samples_sound(tmp_path: Path) -> None:
    cache = write_frame_cache(tmp_path / "cache" / "frames" / "tiny")

    register = measured_register(cache, positions=np.arange(cache.sample_count), reader=subharmonic_reader())

    lowest, highest = _comb_semitones(cache)
    assert register.lowest_semitones >= lowest - READING_TOLERANCE_SEMITONES
    assert register.highest_semitones <= highest + READING_TOLERANCE_SEMITONES
    assert register.lowest_semitones < register.highest_semitones


def _comb_semitones(cache: FrameCache) -> tuple[float, float]:
    """Where the cache's combs stand, read off the frames rather than the reader."""
    peaks = [
        float(np.argmax(cache.frames[position, STORED_READING, 0].astype(np.float32)))
        for position in range(cache.sample_count)
    ]
    frequencies = ANALYSIS.band_frequencies_hz()
    semitones = [semitones_from_reference(float(frequencies[int(peak)])) for peak in peaks]
    return min(semitones), max(semitones)
