from __future__ import annotations

import io
import json
from dataclasses import dataclass, replace
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
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.codecs import SampleCodec
from samplemorph.codecs.identity import IdentityCodec
from samplemorph.geometry import mel_geometry
from samplemorph.model_store import PRINCIPAL_COMPONENT_CODEC_NAME, MorphModel, MorphModelDescription
from samplemorph.morphers.linear import LinearMorpher
from samplemorph.pipeline import (
    EncodedPair,
    HeardSample,
    LoadedRoute,
    MorphRenderSummary,
    MorphRoute,
    RouteChoice,
    StoredFile,
    common_rate,
    decode_to_audio,
    encode_pair,
    encode_sample,
    encode_waveform,
    listening_set_manifest,
    read_heard_sample,
    render_listening_set,
    render_morph,
)
from samplemorph.registries import CANONICALIZER_REGISTRY, DEFAULT_CANONICALIZER_NAME
from samplemorph.rendering import (
    FULL_SCALE_CEILING,
    RENDER_REVISION,
    RenderedFile,
    RenderKind,
    wav_bytes,
    write_rendering,
)
from samplemorph.vocoders.pghi import PghiVocoder
from tests.samplemorph.conftest import harmonic_tone

FIRST_RATE_HZ = 8_363
SECOND_RATE_HZ = 16_726
NOTE_EVENT_RATE_HZ = 4_181
SAMPLE_FRAME_COUNT = 4096
EXPECTED_FILE_COUNT = 7
PITCH_WINDOW_OCTAVES = 1.0 / 12.0


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


def _stored_pair(
    connection: Connection, library_root: Path, *, canonicalizer: Canonicalizer, codec: SampleCodec
) -> EncodedPair:
    first_sample = _store_sample(connection, library_root, index=1, frequency=220.0, rate_hz=FIRST_RATE_HZ)
    second_sample = _store_sample(connection, library_root, index=2, frequency=660.0, rate_hz=SECOND_RATE_HZ)
    return encode_pair(
        read_heard_sample(connection, SampleAudio.from_catalog(connection, library_root), first_sample),
        read_heard_sample(connection, SampleAudio.from_catalog(connection, library_root), second_sample),
        canonicalizer=canonicalizer,
        codec=codec,
    )


def _heard_tone(index: int, *, frequency: float, rate_hz: int) -> HeardSample:
    sample = Sample(
        hash=format(index, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=SAMPLE_FRAME_COUNT
    )
    return HeardSample(
        sample=sample, pcm=harmonic_tone(SAMPLE_FRAME_COUNT, frequency=frequency), rate_hz=float(rate_hz)
    )


def _dominant_frequency(waveform: np.ndarray, *, rate_hz: float) -> float:
    magnitudes = np.abs(np.fft.rfft(waveform))
    frequencies = np.fft.rfftfreq(waveform.shape[0], d=1.0 / rate_hz)
    return float(frequencies[np.argmax(magnitudes)])


def _level_near(waveform: np.ndarray, *, rate_hz: float, frequency_hz: float) -> float:
    """The strongest magnitude within a semitone of `frequency_hz`."""
    magnitudes = np.abs(np.fft.rfft(waveform))
    frequencies = np.fft.rfftfreq(waveform.shape[0], d=1.0 / rate_hz)
    within = np.abs(np.log2(np.maximum(frequencies, 1e-9) / frequency_hz)) <= PITCH_WINDOW_OCTAVES
    return float(magnitudes[within].max())


def test_a_rendered_listening_set_writes_both_ends_and_every_morph(connection: Connection, tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    canonicalizer = CANONICALIZER_REGISTRY[DEFAULT_CANONICALIZER_NAME]()
    codec = IdentityCodec(canonicalizer.geometry)

    summary = render_listening_set(
        _stored_pair(connection, library_root, canonicalizer=canonicalizer, codec=codec),
        route=MorphRoute(canonicalizer=canonicalizer, codec=codec, vocoder=PghiVocoder(), morpher=LinearMorpher()),
        output_directory=tmp_path / "render",
    )

    assert len(summary.files) == EXPECTED_FILE_COUNT
    assert summary.morph_count == 3
    assert all(file.path.exists() for file in summary.files)
    assert {file.kind for file in summary.files} == set(RenderKind)


def test_the_originals_state_their_own_rates_and_every_other_file_the_rate_the_pair_is_heard_at(
    connection: Connection, tmp_path: Path
) -> None:
    """Writing the nominal 44,100 Hz instead would play an 8,363 Hz sample five times too fast."""
    library_root = tmp_path / "library"
    canonicalizer = CANONICALIZER_REGISTRY[DEFAULT_CANONICALIZER_NAME]()
    codec = IdentityCodec(canonicalizer.geometry)

    summary = render_listening_set(
        _stored_pair(connection, library_root, canonicalizer=canonicalizer, codec=codec),
        route=MorphRoute(canonicalizer=canonicalizer, codec=codec, vocoder=PghiVocoder(), morpher=LinearMorpher()),
        output_directory=tmp_path / "render",
    )

    written = {file.path.name: soundfile.info(file.path).samplerate for file in summary.files}
    assert written["original_first.wav"] == FIRST_RATE_HZ
    assert written["original_second.wav"] == SECOND_RATE_HZ
    assert {
        written["reconstruction_first.wav"],
        written["morph_050.wav"],
        written["reconstruction_second.wav"],
    } == {SECOND_RATE_HZ}
    assert SECOND_RATE_HZ != audio_store.NOMINAL_WAV_RATE


def test_each_end_of_a_pair_keeps_its_heard_pitch_and_the_midpoint_holds_both() -> None:
    """Two tones an octave apart in rate blend in one frame: neither end's pitch moves, and halfway
    carries both pitches rather than the one a glide between the rates would pass through."""
    canonicalizer = CANONICALIZER_REGISTRY[DEFAULT_CANONICALIZER_NAME]()
    codec = IdentityCodec(canonicalizer.geometry)
    route = MorphRoute(canonicalizer=canonicalizer, codec=codec, vocoder=PghiVocoder(), morpher=LinearMorpher())
    pair = encode_pair(
        _heard_tone(1, frequency=220.0, rate_hz=FIRST_RATE_HZ),
        _heard_tone(2, frequency=330.0, rate_hz=SECOND_RATE_HZ),
        canonicalizer=canonicalizer,
        codec=codec,
    )
    first_pitch = 220.0 * FIRST_RATE_HZ / audio_store.NOMINAL_WAV_RATE
    second_pitch = 330.0 * SECOND_RATE_HZ / audio_store.NOMINAL_WAV_RATE
    glide_pitch = float(np.sqrt(first_pitch * second_pitch))

    start = render_morph(pair.first_latent, pair.second_latent, weight=0.0, route=route)
    halfway = render_morph(pair.first_latent, pair.second_latent, weight=0.5, route=route)
    end = render_morph(pair.first_latent, pair.second_latent, weight=1.0, route=route)

    assert abs(np.log2(_dominant_frequency(start, rate_hz=pair.rate_hz) / first_pitch)) < PITCH_WINDOW_OCTAVES
    assert abs(np.log2(_dominant_frequency(end, rate_hz=pair.rate_hz) / second_pitch)) < PITCH_WINDOW_OCTAVES
    at_glide = _level_near(halfway, rate_hz=pair.rate_hz, frequency_hz=glide_pitch)
    assert _level_near(halfway, rate_hz=pair.rate_hz, frequency_hz=first_pitch) > at_glide
    assert _level_near(halfway, rate_hz=pair.rate_hz, frequency_hz=second_pitch) > at_glide


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
            SampleAudio.from_catalog(connection, library_root),
            sample,
            canonicalizer=canonicalizer,
            codec=IdentityCodec(canonicalizer.geometry),
        )


def test_the_note_events_rate_wins_over_the_occurrences_when_the_catalog_holds_one(
    connection: Connection, tmp_path: Path
) -> None:
    """The listening sets and the application agree on the rate a sample is heard at."""
    library_root = tmp_path / "library"
    sample = _store_sample(connection, library_root, index=1, frequency=220.0, rate_hz=FIRST_RATE_HZ)
    PostgresSamplePlaybackRateRepository(connection).replace_all({sample.hash: NOTE_EVENT_RATE_HZ})
    connection.commit()
    canonicalizer = CANONICALIZER_REGISTRY[DEFAULT_CANONICALIZER_NAME]()

    encoded = encode_sample(
        connection,
        SampleAudio.from_catalog(connection, library_root),
        sample,
        canonicalizer=canonicalizer,
        codec=IdentityCodec(canonicalizer.geometry),
    )

    assert encoded.rate_hz == NOTE_EVENT_RATE_HZ


def test_a_morph_at_the_first_endpoint_is_that_sample_s_own_reconstruction() -> None:
    canonicalizer = CANONICALIZER_REGISTRY[DEFAULT_CANONICALIZER_NAME]()
    codec = IdentityCodec(canonicalizer.geometry)
    route = MorphRoute(canonicalizer=canonicalizer, codec=codec, vocoder=PghiVocoder(), morpher=LinearMorpher())
    first = encode_waveform(
        harmonic_tone(SAMPLE_FRAME_COUNT, frequency=220.0), canonicalizer=canonicalizer, codec=codec
    )
    second = encode_waveform(
        harmonic_tone(2 * SAMPLE_FRAME_COUNT, frequency=660.0), canonicalizer=canonicalizer, codec=codec
    )

    endpoint = render_morph(first.latent, second.latent, weight=0.0, route=route)
    halfway = render_morph(first.latent, second.latent, weight=0.5, route=route)

    np.testing.assert_array_equal(endpoint, decode_to_audio(first.latent, route=route))
    assert SAMPLE_FRAME_COUNT < halfway.shape[0] < 2 * SAMPLE_FRAME_COUNT


@dataclass(frozen=True)
class LevelCase:
    peak: float
    written_peak: float


@pytest.mark.parametrize(
    "case",
    [LevelCase(peak=0.1, written_peak=0.1), LevelCase(peak=4.0, written_peak=FULL_SCALE_CEILING)],
    ids=("a quiet waveform keeps its level", "a loud one is lowered below full scale"),
)
def test_wav_bytes_read_back_at_the_stated_rate_and_level(case: LevelCase) -> None:
    waveform = np.linspace(-case.peak, case.peak, 512)

    frames, rate = soundfile.read(io.BytesIO(wav_bytes(waveform, rate_hz=FIRST_RATE_HZ)))

    assert rate == FIRST_RATE_HZ
    assert frames.shape[0] == waveform.shape[0]
    assert float(np.abs(frames).max()) == pytest.approx(case.written_peak, abs=1.0 / 16384)


def test_a_pair_is_heard_at_the_higher_of_its_two_rates() -> None:
    """The faster sample keeps its whole band, and the slower one gains frames and loses nothing."""
    assert common_rate(FIRST_RATE_HZ, SECOND_RATE_HZ) == SECOND_RATE_HZ
    assert common_rate(SECOND_RATE_HZ, FIRST_RATE_HZ) == SECOND_RATE_HZ


def test_a_rendered_file_keeps_a_quiet_waveform_at_its_level(tmp_path: Path) -> None:
    quiet = np.linspace(-0.2, 0.2, 512)

    written = write_rendering(
        RenderedFile(path=tmp_path / "quiet.wav", kind=RenderKind.ORIGINAL, rate_hz=FIRST_RATE_HZ, weight=None), quiet
    )

    frames, _ = soundfile.read(written.path)
    assert float(np.abs(frames).max()) == pytest.approx(0.2, abs=1.0 / 16384)


def test_note_matches_the_reference_key_the_library_counts_from() -> None:
    """Tracker C-5 is the key an occurrence's rate is stated at, which the render path assumes."""
    assert Note(60).midi == 72


def test_a_listening_set_manifest_names_the_samples_the_route_and_its_files() -> None:
    """A set is judged by ear days later, so it has to say which samples and which route produced it."""
    description = MorphModelDescription(
        codec=PRINCIPAL_COMPONENT_CODEC_NAME,
        canonicalizer="mel",
        geometry=mel_geometry(),
        latent_size=4,
        fitted_sample_count=12,
        random_seed=0,
        explained_variance=0.9,
    )
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    loaded = LoadedRoute(
        model=MorphModel(description=description, codec=IdentityCodec(canonicalizer.geometry)),
        route=MorphRoute(
            canonicalizer=canonicalizer,
            codec=IdentityCodec(canonicalizer.geometry),
            vocoder=PghiVocoder(),
            morpher=LinearMorpher(),
        ),
        choice=RouteChoice(
            model_name="pca", vocoder_name="pghi", restorer_name="restorer", morpher_name="linear", device="cpu"
        ),
        files=(StoredFile(path=Path("models/pca.npz"), sha256="c" * 64),),
    )
    summary = MorphRenderSummary(
        first_hash="a" * 64,
        second_hash="b" * 64,
        files=(RenderedFile(path=Path("morph_050.wav"), kind=RenderKind.MORPH, rate_hz=8363.0, weight=0.5),),
    )

    manifest = json.loads(listening_set_manifest(loaded, summary))

    assert manifest["first_hash"] == "a" * 64
    assert manifest["second_hash"] == "b" * 64
    assert manifest["model"]["canonicalizer"] == "mel"
    assert (manifest["vocoder"], manifest["restorer"], manifest["morpher"], manifest["device"]) == (
        "pghi",
        None,
        "linear",
        "cpu",
    )
    assert manifest["loaded_files"] == [{"path": "models/pca.npz", "sha256": "c" * 64}]
    assert manifest["fingerprint"] == loaded.fingerprint
    assert manifest["render_revision"] == RENDER_REVISION
    assert manifest["files"] == [{"name": "morph_050.wav", "kind": "morph", "rate_hz": 8363.0, "weight": 0.5}]


def test_the_fingerprint_follows_the_vocoder_and_the_file_bytes() -> None:
    description = MorphModelDescription(
        codec=PRINCIPAL_COMPONENT_CODEC_NAME,
        canonicalizer="mel",
        geometry=mel_geometry(),
        latent_size=4,
        fitted_sample_count=12,
        random_seed=0,
        explained_variance=0.9,
    )
    canonicalizer = CANONICALIZER_REGISTRY["mel"]()
    loaded = LoadedRoute(
        model=MorphModel(description=description, codec=IdentityCodec(canonicalizer.geometry)),
        route=MorphRoute(
            canonicalizer=canonicalizer,
            codec=IdentityCodec(canonicalizer.geometry),
            vocoder=PghiVocoder(),
            morpher=LinearMorpher(),
        ),
        choice=RouteChoice(
            model_name="pca", vocoder_name="pghi", restorer_name="restorer", morpher_name="linear", device="cpu"
        ),
        files=(StoredFile(path=Path("models/pca.npz"), sha256="c" * 64),),
    )

    assert replace(loaded, choice=replace(loaded.choice, vocoder_name="restored")).fingerprint != loaded.fingerprint
    assert (
        replace(loaded, files=(StoredFile(path=Path("models/pca.npz"), sha256="d" * 64),)).fingerprint
        != loaded.fingerprint
    )
    assert replace(loaded, choice=replace(loaded.choice, model_name="renamed")).fingerprint == loaded.fingerprint
