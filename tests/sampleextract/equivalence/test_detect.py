from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

import numpy as np
import pytest
import soundfile
from numpy.typing import NDArray
from scipy.signal import resample_poly
from sqlalchemy import Connection
from trackmod.binary.pcm.quantize import dequantize, quantize
from trackmod.core.samples.depth import BitDepth

import sampleextract.equivalence.detect as detect_module
from samplecore.models.channels import ChannelLayout
from samplecore.models.relation import RelationType
from samplecore.models.sample import Sample
from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.models.sample_pcm import SamplePCM
from samplecore.process_pool import IN_PROCESS_WORKERS
from samplecore.sample_files.decoding import decode_sample_file
from samplecore.storage import audio_store
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.fingerprint import PostgresSampleFingerprintRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio
from sampleextract.equivalence.detect import EquivalenceSummary, detect_equivalences
from sampleextract.equivalence.fingerprint import FINGERPRINT_VERSION
from sampleextract.equivalence.fingerprinting import FingerprintedSamples
from sampleextract.equivalence.pairs import WaveformCache
from sampleextract.files.ingest import ingest_sample_file

SAMPLE_RATE = 44100
TWO_WORKERS: Final[int] = 2
WORKER_COUNTS: Final[tuple[int, ...]] = (IN_PROCESS_WORKERS, TWO_WORKERS)
WORKER_COUNT_IDS: Final[tuple[str, ...]] = ("in process", "two workers")


def _tonal_waveform(frames: int) -> NDArray[np.float64]:
    time = np.arange(frames) / SAMPLE_RATE
    waveform = (
        0.5 * np.sin(2 * np.pi * 220 * time)
        + 0.3 * np.sin(2 * np.pi * 440 * time)
        + 0.2 * np.sin(2 * np.pi * 880 * time)
    )
    return waveform.reshape(-1, 1)


def _store_sample(
    connection: Connection,
    library_root: Path,
    *,
    hash_seed: int,
    depth: BitDepth,
    pcm: NDArray[np.float64],
) -> Sample:
    sample = Sample(hash=format(hash_seed, "064x"), depth=depth, channels=ChannelLayout.MONO, frames=pcm.shape[0])
    PostgresSampleRepository(connection).upsert(sample)
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
    return sample


def _store_sample_file(library_root: Path, *, hash_seed: int, pcm: NDArray[np.float64]) -> Sample:
    sample = Sample(
        hash=format(hash_seed, "064x"), depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=pcm.shape[0]
    )
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
    return sample


def _seed_catalog(connection: Connection, library_root: Path) -> tuple[Sample, Sample, Sample, Sample, Sample]:
    """A catalog holding one genuine bit-depth-variant pair, one genuine amplification-variant pair
    that also changes depth (the compound case a gain-insensitive scorer would miss), one genuine
    resampled-variant pair, and unrelated content sharing frame counts with each, so every detector
    has a real reject case alongside the pair it is meant to find.
    """
    original_16_pcm = _tonal_waveform(2500)
    quantized_8_pcm = dequantize(quantize(original_16_pcm, BitDepth.EIGHT), BitDepth.EIGHT)
    unrelated_bit_depth_pcm = np.random.default_rng(101).uniform(-1.0, 1.0, (2500, 1))

    original_44k_pcm = _tonal_waveform(4410)
    resampled_22k_pcm = resample_poly(original_44k_pcm, up=22050, down=44100, axis=0)
    unrelated_resampled_pcm = np.random.default_rng(202).uniform(-1.0, 1.0, (2205, 1))

    louder_original_pcm = _tonal_waveform(1600)
    quieter_and_requantized_pcm = dequantize(quantize(louder_original_pcm * 0.25, BitDepth.EIGHT), BitDepth.EIGHT)

    original_16 = _store_sample(connection, library_root, hash_seed=1, depth=BitDepth.SIXTEEN, pcm=original_16_pcm)
    quantized_8 = _store_sample(connection, library_root, hash_seed=2, depth=BitDepth.EIGHT, pcm=quantized_8_pcm)
    _store_sample(connection, library_root, hash_seed=3, depth=BitDepth.EIGHT, pcm=unrelated_bit_depth_pcm)

    original_44k = _store_sample(connection, library_root, hash_seed=4, depth=BitDepth.SIXTEEN, pcm=original_44k_pcm)
    resampled_22k = _store_sample(connection, library_root, hash_seed=5, depth=BitDepth.SIXTEEN, pcm=resampled_22k_pcm)
    _store_sample(connection, library_root, hash_seed=6, depth=BitDepth.SIXTEEN, pcm=unrelated_resampled_pcm)

    louder_original = _store_sample(
        connection, library_root, hash_seed=7, depth=BitDepth.SIXTEEN, pcm=louder_original_pcm
    )
    quieter_and_requantized = _store_sample(
        connection, library_root, hash_seed=8, depth=BitDepth.EIGHT, pcm=quieter_and_requantized_pcm
    )

    return original_16, quantized_8, original_44k, resampled_22k, louder_original


@pytest.mark.parametrize("workers", WORKER_COUNTS, ids=WORKER_COUNT_IDS)
def test_detect_equivalences_records_exactly_the_genuine_pairs(
    connection: Connection, tmp_path: Path, workers: int
) -> None:
    original_16, quantized_8, original_44k, resampled_22k, louder_original = _seed_catalog(connection, tmp_path)

    summary = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path), workers=workers)

    relations = PostgresSampleRelationRepository(connection).list_all()
    assert summary.samples_considered == 8
    assert summary.bit_depth_relations == 1
    assert summary.amplification_relations == 1
    assert summary.resampled_relations == 1
    assert len(relations) == 3

    found_pairs = {frozenset((relation.subject_hash, relation.reference_hash)) for relation in relations}
    assert frozenset((original_16.hash, quantized_8.hash)) in found_pairs
    assert frozenset((original_44k.hash, resampled_22k.hash)) in found_pairs

    relation_by_type = {relation.relation_type: relation for relation in relations}
    assert relation_by_type[RelationType.BIT_DEPTH_VARIANT].method == "bit_depth_variant/gain_lstsq_v1"
    assert relation_by_type[RelationType.RESAMPLED_VARIANT].method == "resampled_variant/xcorr_v1"
    assert relation_by_type[RelationType.RESAMPLED_VARIANT].evidence["depth_changed"] == 0.0

    amplification_relation = relation_by_type[RelationType.AMPLIFICATION_VARIANT]
    assert amplification_relation.method == "amplification_variant/gain_lstsq_v1"
    assert amplification_relation.evidence["depth_changed"] == 1.0
    assert amplification_relation.evidence["gain"] == pytest.approx(0.25, abs=0.01)
    assert louder_original.hash in (amplification_relation.subject_hash, amplification_relation.reference_hash)


def test_a_second_run_leaves_the_same_relations_in_place(connection: Connection, tmp_path: Path) -> None:
    _seed_catalog(connection, tmp_path)
    detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))

    detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))

    assert len(PostgresSampleRelationRepository(connection).list_all()) == 3


def test_sample_limit_restricts_the_considered_sample_count(connection: Connection, tmp_path: Path) -> None:
    _seed_catalog(connection, tmp_path)

    summary = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path), sample_limit=2)

    assert summary.samples_considered == 2


def test_sample_limit_of_zero_finds_nothing(connection: Connection, tmp_path: Path) -> None:
    _seed_catalog(connection, tmp_path)

    summary = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path), sample_limit=0)

    assert summary == EquivalenceSummary(
        samples_considered=0,
        silent_samples=0,
        unavailable_samples=0,
        unavailable_pairs=0,
        gain_candidates=0,
        resampled_candidates=0,
        bit_depth_relations=0,
        amplification_relations=0,
        resampled_relations=0,
    )


def test_a_negative_sample_limit_is_refused(connection: Connection, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 0"):
        detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path), sample_limit=-1)


def _candidates(summary: EquivalenceSummary) -> int:
    return summary.gain_candidates + summary.resampled_candidates


def _relation_pairs(connection: Connection) -> set[tuple[str, str, RelationType]]:
    return {
        (relation.subject_hash, relation.reference_hash, relation.relation_type)
        for relation in PostgresSampleRelationRepository(connection).list_all()
    }


def _compared_anew(connection: Connection, tmp_path: Path) -> EquivalenceSummary:
    """A pass comparing every sample again, as `--force` asks for."""
    with start_batch(connection):
        PostgresSampleFingerprintRepository(connection).forget_comparisons()
    return detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))


def test_a_pass_stopped_partway_keeps_its_blocks_and_a_rerun_compares_only_the_rest(
    connection: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_catalog(connection, tmp_path)
    monkeypatch.setattr(detect_module, "NEIGHBOR_BLOCK_ROWS", 1)
    record = detect_module._Comparison._record

    def fail_after_the_first_block_with_relations(comparison: Any, submitted: Any) -> None:
        if PostgresSampleRelationRepository(connection).list_all():
            raise OSError("simulated failure")
        record(comparison, submitted)

    monkeypatch.setattr(detect_module._Comparison, "_record", fail_after_the_first_block_with_relations)
    with pytest.raises(OSError):
        detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))
    kept = PostgresSampleRelationRepository(connection).list_all()
    monkeypatch.setattr(detect_module._Comparison, "_record", record)

    rerun = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))

    assert 0 < len(kept) < 3
    assert len(PostgresSampleRelationRepository(connection).list_all()) == 3
    assert _candidates(rerun) < _candidates(_compared_anew(connection, tmp_path))


def test_a_grown_catalog_compares_only_its_new_samples_and_ends_as_a_full_pass_would(
    connection: Connection, tmp_path: Path
) -> None:
    _seed_catalog(connection, tmp_path)
    detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))
    tone = _tonal_waveform(3300) * 0.8
    _store_sample(connection, tmp_path, hash_seed=51, depth=BitDepth.SIXTEEN, pcm=tone)
    _store_sample(
        connection,
        tmp_path,
        hash_seed=52,
        depth=BitDepth.EIGHT,
        pcm=dequantize(quantize(tone, BitDepth.EIGHT), BitDepth.EIGHT),
    )

    grown = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))
    found = _relation_pairs(connection)
    full = _compared_anew(connection, tmp_path)

    assert grown.bit_depth_relations == 1
    assert 0 < _candidates(grown) < _candidates(full)
    assert _relation_pairs(connection) == found


def test_a_new_comparison_rule_compares_every_sample_again(
    connection: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_catalog(connection, tmp_path)
    first = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))
    unchanged = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))
    monkeypatch.setattr(detect_module, "COMPARISON_VERSION", detect_module.COMPARISON_VERSION + 1)

    renewed = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))

    assert _candidates(unchanged) == 0
    assert _candidates(renewed) == _candidates(first)


def test_silent_samples_are_counted_and_left_out_of_every_comparison(connection: Connection, tmp_path: Path) -> None:
    """Silence of two different lengths holds no content a relation could be about, pass after pass."""
    _store_sample(connection, tmp_path, hash_seed=21, depth=BitDepth.SIXTEEN, pcm=np.zeros((1024, 1)))
    _store_sample(connection, tmp_path, hash_seed=22, depth=BitDepth.EIGHT, pcm=np.zeros((2048, 1)))

    first = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))
    second = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))

    assert (first.silent_samples, second.silent_samples) == (2, 2)
    assert PostgresSampleRelationRepository(connection).list_all() == ()
    assert all(
        stored.fingerprint.silent
        for stored in PostgresSampleFingerprintRepository(connection).at_version(FINGERPRINT_VERSION).values()
    )


def test_a_trimmed_tail_pair_is_recorded_once_as_the_gain_variant_it_is(connection: Connection, tmp_path: Path) -> None:
    content = _tonal_waveform(3000) * 0.5
    _store_sample(connection, tmp_path, hash_seed=31, depth=BitDepth.SIXTEEN, pcm=content)
    _store_sample(connection, tmp_path, hash_seed=32, depth=BitDepth.SIXTEEN, pcm=np.pad(content, ((0, 20), (0, 0))))

    summary = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))

    assert (summary.amplification_relations, summary.resampled_relations) == (1, 0)


def test_the_waveform_cache_lets_the_oldest_waveforms_go_once_its_budget_is_spent(tmp_path: Path) -> None:
    samples = [_store_sample_file(tmp_path, hash_seed=seed, pcm=_tonal_waveform(1000)) for seed in range(41, 44)]
    cache = WaveformCache(SampleAudio.of_files(tmp_path, ()), byte_budget=2 * 1000 * 8)

    for sample in samples:
        cache.get(sample)

    assert list(cache._waveforms) == [samples[1].hash, samples[2].hash]


def test_detect_equivalences_finds_a_pair_differing_only_by_a_trimmed_silent_tail(
    connection: Connection, tmp_path: Path
) -> None:
    """A pair whose only difference is a genuinely-silent trailing tail shares depth, so it must not
    be misreported as a bit-depth variant -- it is classified as an amplification variant instead,
    the closer of the two labels available, carrying a recovered gain of 1.0.
    """
    content = np.full((1600, 1), 0.5)
    with_silent_tail = np.pad(content, ((0, 50), (0, 0)))

    without_tail = _store_sample(connection, tmp_path, hash_seed=11, depth=BitDepth.SIXTEEN, pcm=content)
    with_tail = _store_sample(connection, tmp_path, hash_seed=12, depth=BitDepth.SIXTEEN, pcm=with_silent_tail)

    summary = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))

    assert summary.amplification_relations == 1
    assert summary.bit_depth_relations == 0
    relations = PostgresSampleRelationRepository(connection).list_all()
    relation = next(
        relation
        for relation in relations
        if {relation.subject_hash, relation.reference_hash} == {without_tail.hash, with_tail.hash}
    )
    assert relation.relation_type == RelationType.AMPLIFICATION_VARIANT
    assert relation.evidence["depth_changed"] == 0.0
    assert relation.evidence["gain"] == pytest.approx(1.0)


@pytest.mark.parametrize("workers", WORKER_COUNTS, ids=WORKER_COUNT_IDS)
def test_a_sample_whose_file_is_gone_is_counted_and_the_rest_are_still_compared(
    connection: Connection, tmp_path: Path, vanished_sample_file: SampleFile, workers: int
) -> None:
    _seed_catalog(connection, tmp_path)

    summary = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path), workers=workers)

    assert summary.unavailable_samples == 1
    assert summary.bit_depth_relations + summary.amplification_relations + summary.resampled_relations > 0


def test_a_pair_whose_file_goes_missing_while_the_pass_runs_is_left_for_a_later_pass(
    connection: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "pack"
    directory.mkdir()
    loud, quiet = directory / "tone.wav", directory / "tone quiet.wav"
    soundfile.write(loud, _tonal_waveform(4096), SAMPLE_RATE, subtype="PCM_16")
    soundfile.write(quiet, 0.5 * _tonal_waveform(4096), SAMPLE_RATE, subtype="PCM_16")
    for path in (loud, quiet):
        ingest_sample_file(
            connection,
            location=SampleFileLocation(directory=directory, relative_path=path.name),
            decoded=decode_sample_file(path),
            fingerprint=FileFingerprint.of(path.stat()),
        )
    fingerprint_samples = detect_module.fingerprint_samples
    content, written = quiet.read_bytes(), quiet.stat()

    def unplug_once_fingerprinted(*arguments: Any, **keywords: Any) -> FingerprintedSamples:
        fingerprinted = fingerprint_samples(*arguments, **keywords)
        quiet.unlink()
        return fingerprinted

    monkeypatch.setattr(detect_module, "fingerprint_samples", unplug_once_fingerprinted)

    summary = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))
    monkeypatch.setattr(detect_module, "fingerprint_samples", fingerprint_samples)
    quiet.write_bytes(content)
    os.utime(quiet, ns=(written.st_atime_ns, written.st_mtime_ns))
    later = detect_equivalences(connection, SampleAudio.from_catalog(connection, tmp_path))

    assert (summary.unavailable_samples, summary.unavailable_pairs) == (0, 1)
    assert later.amplification_relations == 1
