from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplecore.waveform import resample_by_semitones
from samplemorph.canonicalizers.common import PreparedMono, prepare_mono
from samplemorph.coordinates.readers import (
    PyinReader,
    SubharmonicReader,
    parabolic_offset,
    pyin_reader,
    subharmonic_reader,
)
from samplemorph.geometry import semitones_from_reference
from samplemorph.tones import HarmonicTone, harmonic_tone

RATE_HZ = 44100.0
SUBHARMONIC_TOLERANCE_SEMITONES = 0.05
PYIN_TOLERANCE_SEMITONES = 0.1
RETUNING_SEMITONES = 7.0
PLAIN = HarmonicTone(fundamental_hz=110.0, resonance_hz=110.0, resonance_gain_db=0.0)


@dataclass(frozen=True)
class ToneCase:
    label: str
    tone: HarmonicTone


TONE_CASES = (
    ToneCase("plain", PLAIN),
    ToneCase("resonance on the third harmonic", HarmonicTone(fundamental_hz=110.0, resonance_hz=330.0)),
    ToneCase(
        "missing fundamental",
        HarmonicTone(fundamental_hz=150.0, resonance_hz=150.0, resonance_gain_db=0.0, lowest_harmonic=2),
    ),
    ToneCase(
        "stiff string",
        HarmonicTone(fundamental_hz=80.0, resonance_hz=80.0, resonance_gain_db=0.0, inharmonicity=5e-4),
    ),
)


@pytest.fixture(scope="module")
def subharmonic() -> SubharmonicReader:
    return subharmonic_reader()


@pytest.fixture(scope="module")
def pyin() -> PyinReader:
    return pyin_reader()


def _mono(tone: HarmonicTone) -> PreparedMono:
    return prepare_mono(harmonic_tone(tone, rate_hz=RATE_HZ))


def _noise() -> PreparedMono:
    return PreparedMono(0.3 * np.random.default_rng(0).standard_normal(int(RATE_HZ)))


@pytest.mark.parametrize("case", TONE_CASES, ids=lambda case: case.label)
def test_the_subharmonic_reader_places_a_tone_on_its_fundamental(
    case: ToneCase, subharmonic: SubharmonicReader
) -> None:
    reading = subharmonic.read(_mono(case.tone))

    assert reading is not None
    assert (
        abs(reading.semitones - semitones_from_reference(case.tone.fundamental_hz)) <= SUBHARMONIC_TOLERANCE_SEMITONES
    )


def test_the_subharmonic_reader_follows_a_retuning_between_its_bins(subharmonic: SubharmonicReader) -> None:
    mono = _mono(HarmonicTone(fundamental_hz=110.0, resonance_hz=1500.0))

    stored = subharmonic.read(mono)
    retuned = subharmonic.read(PreparedMono(resample_by_semitones(mono, semitones=RETUNING_SEMITONES + 0.5)))

    assert stored is not None and retuned is not None
    assert abs(retuned.semitones - stored.semitones - (RETUNING_SEMITONES + 0.5)) <= SUBHARMONIC_TOLERANCE_SEMITONES


def test_the_subharmonic_reader_trusts_a_tone_over_a_noise(subharmonic: SubharmonicReader) -> None:
    tone, noise = subharmonic.read(_mono(PLAIN)), subharmonic.read(_noise())

    assert tone is not None and noise is not None
    assert tone.reliability > noise.reliability


def test_pyin_places_a_plain_tone_on_its_fundamental(pyin: PyinReader) -> None:
    reading = pyin.read(_mono(PLAIN))

    assert reading is not None
    assert abs(reading.semitones - semitones_from_reference(PLAIN.fundamental_hz)) <= PYIN_TOLERANCE_SEMITONES
    assert 0.0 < reading.reliability <= 1.0


@pytest.mark.parametrize("reader_fixture", ["subharmonic", "pyin"])
def test_a_silent_sound_reads_no_pitch(reader_fixture: str, request: pytest.FixtureRequest) -> None:
    reader: SubharmonicReader | PyinReader = request.getfixturevalue(reader_fixture)

    assert reader.read(PreparedMono(np.zeros(int(RATE_HZ)))) is None


def test_the_parabola_finds_a_peak_between_bins() -> None:
    bins = np.arange(9, dtype=np.float64)

    offset = parabolic_offset(-((bins - 4.3) ** 2), peak=4)

    assert offset == pytest.approx(0.3)
