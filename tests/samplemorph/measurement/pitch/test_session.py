from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers.common import PreparedMono
from samplemorph.measurement.pitch.changes import LevelChange, Retuning
from samplemorph.measurement.pitch.reading import (
    STORED_VARIANT,
    DrawnSample,
    HeldOutReader,
    SyntheticReader,
    variants_of,
)
from samplemorph.measurement.pitch.session import (
    PICTURES_DIRECTORY_NAME,
    READINGS_FILE_NAME,
    RELIABILITY_FILE_NAME,
    SUMMARY_FILE_NAME,
    PitchReadings,
    SyntheticSet,
    write_pitch_readings,
)
from samplemorph.measurement.pitch.synthetic import draw_family_tones, draw_noise_bursts, draw_tone_pairs
from samplemorph.measurement.pitch.tables import trial_rows
from samplemorph.measurement.pitch.trial_sets import family_trials
from samplemorph.tones import HarmonicTone, harmonic_tone
from tests.samplemorph.measurement.pitch.conftest import Reading

READER = "length"
HASH = "d" * 64
PARTNER_HASH = "e" * 64
RATE_HZ = 44100.0


@dataclass(frozen=True)
class LengthReader:
    """A stand-in reader that places a sound by its length, so a retuning reads as the interval it shortens by."""

    @property
    def name(self) -> str:
        return READER

    def read(self, mono: PreparedMono) -> Reading | None:
        return Reading(semitones=-12.0 * float(np.log2(len(mono) / RATE_HZ)), reliability=0.5)


@dataclass(frozen=True)
class FirstHalf:
    """A stand-in morph whose middle is the first sound's first half."""

    @property
    def name(self) -> str:
        return "first-half"

    def middle(self, first: PreparedMono, second: PreparedMono) -> PreparedMono:
        return PreparedMono(first[: len(first) // 2])


def _write(library_root: Path, sample_hash: str) -> None:
    pcm = harmonic_tone(HarmonicTone(fundamental_hz=220.0, resonance_hz=1500.0), rate_hz=RATE_HZ)
    sample = Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=pcm.shape[0])
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))


def test_a_held_out_sample_is_read_as_stored_under_every_change_and_through_every_morph(tmp_path: Path) -> None:
    for sample_hash in (HASH, PARTNER_HASH):
        _write(tmp_path, sample_hash)
    changes, morphs = (Retuning(semitones=12.0), LevelChange(decibels=-20.0)), (FirstHalf(),)

    readings = HeldOutReader(
        audio=SampleAudio.of_files(tmp_path, ()), readers=(LengthReader(),), changes=changes, morphs=morphs
    )(DrawnSample(sample_hash=HASH, partner_hash=PARTNER_HASH))

    names = [STORED_VARIANT, *(variant.name for variant in variants_of(changes, morphs))]
    assert set(readings.readings) == {(name, READER) for name in names}
    stored, retuned = readings.readings[(STORED_VARIANT, READER)], readings.readings[(changes[0].name, READER)]
    assert stored is not None and retuned is not None
    assert abs(retuned.semitones - stored.semitones - 12.0) < 0.01
    assert readings.sound_type == "tonal"


def test_the_readings_are_written_as_one_row_per_trial_a_summary_and_a_picture_per_reader(tmp_path: Path) -> None:
    synthetic = SyntheticSet(
        tones=draw_family_tones(count=1, random_seed=0),
        pairs=draw_tone_pairs(count=2, random_seed=0),
        noises=draw_noise_bursts(count=2, random_seed=0),
    )
    reader = SyntheticReader(readers=(LengthReader(),))
    synthetic_readings = {sound.name: reader(sound) for sound in synthetic.sounds}

    summary = write_pitch_readings(
        PitchReadings(reader_names=(READER,), held_out=(), synthetic=synthetic, synthetic_readings=synthetic_readings),
        variants=(),
        referees=(READER, READER),
        output_directory=tmp_path,
    )

    with (tmp_path / READINGS_FILE_NAME).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected_columns = list(
        trial_rows(family_trials(synthetic.tones[:1], synthetic_readings, reader_names=(READER,)))[0]
    )
    assert len(rows) == summary.trial_count
    assert list(rows[0]) == expected_columns
    assert (tmp_path / SUMMARY_FILE_NAME).is_file() and (tmp_path / RELIABILITY_FILE_NAME).is_file()
    assert (tmp_path / PICTURES_DIRECTORY_NAME / f"{READER}.png").is_file()
