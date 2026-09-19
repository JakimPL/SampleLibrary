from __future__ import annotations

from typing import Final

import numpy as np
import pytest

from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.coordinates.readers import PyinReader, pyin_reader
from samplemorph.envelope.glide import (
    PitchedAnalysis,
    PitchGlide,
    carried_excitation,
    glide_between,
)
from samplemorph.envelope.morph import EnvelopePath
from samplemorph.envelope.settings import EnvelopeSettings, Excitation
from samplemorph.geometry import semitones_from_reference
from samplemorph.transport.analysis import TransportAnalysis
from samplemorph.transport.settings import TransportSettings
from samplemorph.vocoders.pghi import integrate_and_synthesize
from tests.samplemorph.transport.conftest import GEOMETRY, analysis_of, tone

LOW_HZ: Final[float] = 220.0
HIGH_HZ: Final[float] = 330.0
GLIDE: Final[PitchGlide] = PitchGlide(
    first_semitones=semitones_from_reference(LOW_HZ), second_semitones=semitones_from_reference(HIGH_HZ)
)
GLIDE_TOLERANCE_SEMITONES: Final[float] = 0.1
LOBE_BIN: Final[int] = 40
LOBE_HALF_WIDTH: Final[int] = 3


@pytest.fixture(scope="module")
def ends() -> tuple[TransportAnalysis, TransportAnalysis]:
    return analysis_of(tone(LOW_HZ)), analysis_of(tone(HIGH_HZ))


@pytest.fixture(scope="module")
def pyin() -> PyinReader:
    return pyin_reader()


def _pitched(ends: tuple[TransportAnalysis, TransportAnalysis], glide: PitchGlide) -> tuple[PitchedAnalysis, ...]:
    return (
        PitchedAnalysis(analysis=ends[0], pitch_semitones=glide.first_semitones),
        PitchedAnalysis(analysis=ends[1], pitch_semitones=glide.second_semitones),
    )


def _heard_semitones(
    path: EnvelopePath,
    ends: tuple[TransportAnalysis, TransportAnalysis],
    *,
    weight: float,
    glide: PitchGlide,
    reader: PyinReader,
) -> float:
    first, second = _pitched(ends, glide)
    spectrogram = path.gliding(first, second, weight=weight, geometry=GEOMETRY, settings=TransportSettings())
    waveform = integrate_and_synthesize(spectrogram.magnitude, geometry=GEOMETRY, frame_count=spectrogram.sample_count)
    reading = reader.read(prepare_mono(waveform))
    assert reading is not None
    return reading.semitones


@pytest.mark.parametrize("excitation", [Excitation.FIRST, Excitation.SECOND, Excitation.BOTH])
@pytest.mark.parametrize("weight", [0.0, 0.5, 1.0])
def test_a_glide_sounds_the_pitch_its_weight_of_the_way_between_the_ends(
    ends: tuple[TransportAnalysis, TransportAnalysis], pyin: PyinReader, excitation: Excitation, weight: float
) -> None:
    path = EnvelopePath(envelope_settings=EnvelopeSettings(excitation=excitation))

    heard = _heard_semitones(path, ends, weight=weight, glide=GLIDE, reader=pyin)

    expected = GLIDE.first_semitones + weight * GLIDE.interval_semitones
    assert heard == pytest.approx(expected, abs=GLIDE_TOLERANCE_SEMITONES)


def test_with_an_end_of_no_pitch_the_path_renders_as_it_always_has(
    ends: tuple[TransportAnalysis, TransportAnalysis],
) -> None:
    path = EnvelopePath(envelope_settings=EnvelopeSettings(excitation=Excitation.FIRST))
    first, _ = _pitched(ends, GLIDE)

    gliding = path.gliding(
        first,
        PitchedAnalysis(analysis=ends[1], pitch_semitones=None),
        weight=0.5,
        geometry=GEOMETRY,
        settings=TransportSettings(),
    )
    held = path(*ends, weight=0.5, geometry=GEOMETRY, settings=TransportSettings())

    assert np.array_equal(gliding.magnitude, held.magnitude)
    assert gliding.sample_count == held.sample_count


def test_carrying_by_one_leaves_an_excitation_as_it_is() -> None:
    excitation = np.random.default_rng(0).random((64, 3)).astype(np.float32)

    assert carried_excitation(excitation, ratio=1.0) is excitation


def test_a_comb_carried_an_octave_up_lands_each_lobe_at_twice_its_bin_with_its_energy() -> None:
    bins = np.arange(512, dtype=np.float64)
    comb = sum(np.exp(-0.5 * ((bins - center) / 1.5) ** 2) for center in range(LOBE_BIN, 512, LOBE_BIN)) + 1e-4
    excitation = np.sqrt(comb)[:, None].astype(np.float32)

    carried = carried_excitation(excitation, ratio=2.0)[:, 0].astype(np.float64) ** 2

    around = slice(2 * LOBE_BIN - LOBE_HALF_WIDTH, 2 * LOBE_BIN + LOBE_HALF_WIDTH + 1)
    assert 2 * LOBE_BIN - LOBE_HALF_WIDTH + int(np.argmax(carried[around])) == 2 * LOBE_BIN
    assert carried[around].sum() == pytest.approx(
        comb[LOBE_BIN - LOBE_HALF_WIDTH : LOBE_BIN + LOBE_HALF_WIDTH + 1].sum(), rel=0.05
    )
    assert carried[3 * LOBE_BIN] < 1e-2


def test_a_glide_between_high_notes_smooths_the_envelope_past_their_harmonic_combs() -> None:
    settings = EnvelopeSettings()
    high = PitchGlide(first_semitones=0.0, second_semitones=semitones_from_reference(2000.0))

    kept = GLIDE.envelope_settings(settings, geometry=GEOMETRY).coefficient_count
    smoothed = high.envelope_settings(settings, geometry=GEOMETRY).coefficient_count

    comb_bins = 2000.0 * GEOMETRY.fft_length / GEOMETRY.analysis_rate_hz
    assert kept == settings.coefficient_count
    assert smoothed == int((GEOMETRY.fft_length // 2 + 1) / comb_bins)


def test_a_pair_glides_only_when_both_ends_sound_a_pitch(ends: tuple[TransportAnalysis, TransportAnalysis]) -> None:
    pitched = PitchedAnalysis(analysis=ends[0], pitch_semitones=GLIDE.first_semitones)
    unpitched = PitchedAnalysis(analysis=ends[1], pitch_semitones=None)

    assert glide_between(pitched, pitched) == PitchGlide(
        first_semitones=GLIDE.first_semitones, second_semitones=GLIDE.first_semitones
    )
    assert glide_between(pitched, unpitched) is None
