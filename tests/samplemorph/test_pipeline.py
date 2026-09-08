from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import soundfile
from sqlalchemy import Connection
from trackmod.core.notes.pitch import Note
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplemorph.codecs.identity import IdentityCodec
from samplemorph.morphers.linear import LinearMorpher
from samplemorph.pipeline import encode_sample, render_listening_set
from samplemorph.registries import CANONICALIZER_REGISTRY
from samplemorph.rendering import RenderKind, rate_between, write_rendering
from samplemorph.vocoders.griffin_lim import GriffinLimVocoder
from tests.samplemorph.conftest import harmonic_tone

FIRST_RATE_HZ = 8_363
SECOND_RATE_HZ = 16_726
SAMPLE_FRAME_COUNT = 4096
FAST_ITERATIONS = 2
EXPECTED_FILE_COUNT = 7


def _store_sample(connection: Connection, library_root: Path, *, index: int, frequency: float, rate_hz: int) -> Sample:
    """Put one synthetic sample in the catalog and the content store, with an occurrence naming its rate."""
    pcm = harmonic_tone(SAMPLE_FRAME_COUNT, frequency=frequency)
    sample = Sample(
        hash=format(index, "064x"),
        depth=BitDepth.SIXTEEN,
        channels=ChannelLayout.MONO,
        frames=SAMPLE_FRAME_COUNT,
    )
    PostgresSampleRepository(connection).upsert(sample)
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))

    module_repository = PostgresModuleRepository(connection)
    module = Module(
        id=module_repository.next_id(),
        hash=format(index + 500, "064x"),
        filename=f"module{index}.xm",
        tracker=TrackerFormat.XM,
        title="untitled",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=datetime.now(UTC),
    )
    module_repository.insert(module)
    PostgresSamplePropertiesRepository(connection).upsert(
        XMSampleProperties(
            sample_hash=sample.hash,
            occurrence=SampleOccurrence(module_hash=module.hash, instrument_index=0, sample_slot=0),
            name=f"tone{index}",
            rate=rate_hz,
            volume=64,
            tuning=Tuning(relative_note=0, finetune=0),
        )
    )
    connection.commit()
    return sample


def test_a_rendered_listening_set_writes_both_ends_and_every_morph(connection: Connection, tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    first_sample = _store_sample(connection, library_root, index=1, frequency=220.0, rate_hz=FIRST_RATE_HZ)
    second_sample = _store_sample(connection, library_root, index=2, frequency=660.0, rate_hz=SECOND_RATE_HZ)
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    codec = IdentityCodec(canonicalizer.geometry)

    first = encode_sample(connection, library_root, first_sample, canonicalizer=canonicalizer, codec=codec)
    second = encode_sample(connection, library_root, second_sample, canonicalizer=canonicalizer, codec=codec)
    summary = render_listening_set(
        first,
        second,
        canonicalizer=canonicalizer,
        codec=codec,
        morpher=LinearMorpher(),
        vocoder=GriffinLimVocoder(iterations=FAST_ITERATIONS),
        output_directory=tmp_path / "render",
    )

    assert len(summary.files) == EXPECTED_FILE_COUNT
    assert summary.morph_count == 3
    assert all(file.path.exists() for file in summary.files)
    assert {file.kind for file in summary.files} == set(RenderKind)


def test_a_rendered_file_states_the_rate_its_content_is_heard_at(connection: Connection, tmp_path: Path) -> None:
    """Writing the nominal 44,100 Hz instead would play an 8,363 Hz sample five times too fast."""
    library_root = tmp_path / "library"
    first_sample = _store_sample(connection, library_root, index=1, frequency=220.0, rate_hz=FIRST_RATE_HZ)
    second_sample = _store_sample(connection, library_root, index=2, frequency=660.0, rate_hz=SECOND_RATE_HZ)
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    codec = IdentityCodec(canonicalizer.geometry)

    first = encode_sample(connection, library_root, first_sample, canonicalizer=canonicalizer, codec=codec)
    second = encode_sample(connection, library_root, second_sample, canonicalizer=canonicalizer, codec=codec)
    summary = render_listening_set(
        first,
        second,
        canonicalizer=canonicalizer,
        codec=codec,
        morpher=LinearMorpher(),
        vocoder=GriffinLimVocoder(iterations=FAST_ITERATIONS),
        output_directory=tmp_path / "render",
    )

    written = {file.path.name: soundfile.info(file.path).samplerate for file in summary.files}
    assert written["original_first.wav"] == FIRST_RATE_HZ
    assert written["original_second.wav"] == SECOND_RATE_HZ
    assert written["morph_050.wav"] == round(rate_between(FIRST_RATE_HZ, SECOND_RATE_HZ, 0.5))
    assert written["morph_050.wav"] != audio_store.NOMINAL_WAV_RATE


def test_encoding_a_sample_with_no_cataloged_occurrence_says_so(connection: Connection, tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    sample = Sample(hash="f" * 64, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=SAMPLE_FRAME_COUNT)
    PostgresSampleRepository(connection).upsert(sample)
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=harmonic_tone(SAMPLE_FRAME_COUNT, frequency=440.0)))
    connection.commit()
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()

    with pytest.raises(ValueError, match="playback rate is unknown"):
        encode_sample(
            connection,
            library_root,
            sample,
            canonicalizer=canonicalizer,
            codec=IdentityCodec(canonicalizer.geometry),
        )


def test_the_rate_between_two_samples_runs_through_their_pitches() -> None:
    """Halfway between two rates an octave apart is the octave's midpoint, not its average."""
    halfway = rate_between(FIRST_RATE_HZ, SECOND_RATE_HZ, 0.5)

    assert halfway == pytest.approx(FIRST_RATE_HZ * np.sqrt(2.0))
    assert rate_between(FIRST_RATE_HZ, SECOND_RATE_HZ, 0.0) == pytest.approx(FIRST_RATE_HZ)
    assert rate_between(FIRST_RATE_HZ, SECOND_RATE_HZ, 1.0) == pytest.approx(SECOND_RATE_HZ)


def test_a_rendered_file_carries_headroom_below_full_scale(tmp_path: Path) -> None:
    loud = np.linspace(-4.0, 4.0, 512)

    written = write_rendering(tmp_path / "loud.wav", loud, rate_hz=FIRST_RATE_HZ, kind=RenderKind.ORIGINAL, weight=None)

    frames, _ = soundfile.read(written.path)
    assert float(np.abs(frames).max()) < 1.0


def test_note_matches_the_reference_key_the_library_counts_from() -> None:
    """Tracker C-5 is the key an occurrence's rate is stated at, which the render path assumes."""
    assert Note(60).midi == 72
