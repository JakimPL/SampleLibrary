from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pytest
from numpy.typing import NDArray
from scipy.signal import resample_poly
from trackmod.binary.pcm.quantise import dequantise, quantise
from trackmod.core.samples.depth import BitDepth

import sampleextract.equivalence.detect as detect_module
from samplecore.models.channels import ChannelLayout
from samplecore.models.relation import RelationType
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.storage import audio_store
from samplecore.storage.repositories.relation import DuckDBSampleRelationRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository
from sampleextract.equivalence.detect import EquivalenceSummary, detect_equivalences

SAMPLE_RATE = 44100


def _tonal_waveform(frames: int) -> NDArray[np.float64]:
    time = np.arange(frames) / SAMPLE_RATE
    waveform = (
        0.5 * np.sin(2 * np.pi * 220 * time)
        + 0.3 * np.sin(2 * np.pi * 440 * time)
        + 0.2 * np.sin(2 * np.pi * 880 * time)
    )
    return waveform.reshape(-1, 1)


def _store_sample(
    connection: duckdb.DuckDBPyConnection,
    library_root: Path,
    *,
    hash_seed: int,
    depth: BitDepth,
    pcm: NDArray[np.float64],
) -> Sample:
    sample = Sample(hash=format(hash_seed, "064x"), depth=depth, channels=ChannelLayout.MONO, frames=pcm.shape[0])
    DuckDBSampleRepository(connection).upsert(sample)
    audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
    return sample


def _seed_catalog(connection: duckdb.DuckDBPyConnection, library_root: Path) -> tuple[Sample, Sample, Sample, Sample]:
    """A catalog holding one genuine bit-depth-variant pair, one genuine resampled-variant pair,
    and unrelated content sharing frame counts with each, so both detectors have a real reject
    case alongside the pair they are meant to find.
    """
    original_16_pcm = _tonal_waveform(2500)
    quantised_8_pcm = dequantise(quantise(original_16_pcm, BitDepth.EIGHT), BitDepth.EIGHT)
    unrelated_bit_depth_pcm = np.random.default_rng(101).uniform(-1.0, 1.0, (2500, 1))

    original_44k_pcm = _tonal_waveform(4410)
    resampled_22k_pcm = resample_poly(original_44k_pcm, up=22050, down=44100, axis=0)
    unrelated_resampled_pcm = np.random.default_rng(202).uniform(-1.0, 1.0, (2205, 1))

    original_16 = _store_sample(connection, library_root, hash_seed=1, depth=BitDepth.SIXTEEN, pcm=original_16_pcm)
    quantised_8 = _store_sample(connection, library_root, hash_seed=2, depth=BitDepth.EIGHT, pcm=quantised_8_pcm)
    _store_sample(connection, library_root, hash_seed=3, depth=BitDepth.EIGHT, pcm=unrelated_bit_depth_pcm)

    original_44k = _store_sample(connection, library_root, hash_seed=4, depth=BitDepth.SIXTEEN, pcm=original_44k_pcm)
    resampled_22k = _store_sample(connection, library_root, hash_seed=5, depth=BitDepth.SIXTEEN, pcm=resampled_22k_pcm)
    _store_sample(connection, library_root, hash_seed=6, depth=BitDepth.SIXTEEN, pcm=unrelated_resampled_pcm)

    return original_16, quantised_8, original_44k, resampled_22k


def test_detect_equivalences_records_exactly_the_genuine_pairs(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    original_16, quantised_8, original_44k, resampled_22k = _seed_catalog(connection, tmp_path)

    summary = detect_equivalences(connection, tmp_path)

    relations = DuckDBSampleRelationRepository(connection).list_all()
    assert summary.samples_considered == 6
    assert summary.bit_depth_relations == 1
    assert summary.resampled_relations == 1
    assert len(relations) == 2

    found_pairs = {frozenset((relation.subject_hash, relation.reference_hash)) for relation in relations}
    assert frozenset((original_16.hash, quantised_8.hash)) in found_pairs
    assert frozenset((original_44k.hash, resampled_22k.hash)) in found_pairs

    relation_by_type = {relation.relation_type: relation for relation in relations}
    assert relation_by_type[RelationType.BIT_DEPTH_VARIANT].method == "bit_depth_variant/mse_v1"
    assert relation_by_type[RelationType.RESAMPLED_VARIANT].method == "resampled_variant/xcorr_v1"
    assert relation_by_type[RelationType.RESAMPLED_VARIANT].evidence["depth_changed"] == 0.0


def test_a_second_run_leaves_the_same_relations_in_place(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    _seed_catalog(connection, tmp_path)
    detect_equivalences(connection, tmp_path)

    detect_equivalences(connection, tmp_path)

    assert len(DuckDBSampleRelationRepository(connection).list_all()) == 2


def test_sample_limit_restricts_the_considered_sample_count(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_catalog(connection, tmp_path)

    summary = detect_equivalences(connection, tmp_path, sample_limit=2)

    assert summary.samples_considered == 2


def test_sample_limit_of_zero_finds_nothing(connection: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    _seed_catalog(connection, tmp_path)

    summary = detect_equivalences(connection, tmp_path, sample_limit=0)

    assert summary == EquivalenceSummary(samples_considered=0, bit_depth_relations=0, resampled_relations=0)


def test_a_failure_partway_through_leaves_nothing_committed(
    connection: duckdb.DuckDBPyConnection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_catalog(connection, tmp_path)

    def _failing_fingerprint(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        raise OSError("simulated failure")

    monkeypatch.setattr(detect_module, "compute_fingerprint", _failing_fingerprint)

    with pytest.raises(OSError):
        detect_equivalences(connection, tmp_path)

    assert DuckDBSampleRelationRepository(connection).list_all() == ()
