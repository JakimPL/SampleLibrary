from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection
from tqdm import tqdm

from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.storage import audio_store
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.relation import DuckDBSampleRelationRepository, SampleRelationRepository
from samplecore.storage.repositories.sample import DuckDBSampleRepository, SampleRepository
from samplecore.waveform import trim_trailing_silence
from sampleextract.equivalence.candidates import gain_variant_candidate_pairs, resampled_candidate_pairs
from sampleextract.equivalence.fingerprint import compute_fingerprint
from sampleextract.equivalence.scoring import (
    GAIN_UNITY_TOLERANCE,
    GAIN_VARIANT_MINIMUM_CONFIDENCE,
    RESAMPLED_MINIMUM_CONFIDENCE,
    TRAILING_SILENCE_THRESHOLD,
    RelationScore,
    score_gain_variant,
    score_resampled_variant,
)

BIT_DEPTH_METHOD: Final[str] = "bit_depth_variant/gain_lstsq_v1"
AMPLIFICATION_METHOD: Final[str] = "amplification_variant/gain_lstsq_v1"
RESAMPLED_METHOD: Final[str] = "resampled_variant/xcorr_v1"


@dataclass(frozen=True)
class EquivalenceSummary:
    """What one equivalence-detection pass did, across every sample it considered."""

    samples_considered: int
    bit_depth_relations: int
    amplification_relations: int
    resampled_relations: int


@dataclass
class _WaveformCache:
    """Reads a Sample's trailing-silence-trimmed waveform once, however many candidate pairs it joins.

    Trimming here, rather than in each scorer, means every detector -- and the fingerprinting pass
    candidate generation shares with the resampled detector -- compares the same trimmed content.
    """

    library_root: Path
    _waveforms: dict[str, NDArray[np.float64]] = field(default_factory=dict)

    def get(self, sample: Sample) -> NDArray[np.float64]:
        if sample.hash not in self._waveforms:
            pcm = audio_store.read(self.library_root, sample).pcm
            self._waveforms[sample.hash] = trim_trailing_silence(pcm, threshold=TRAILING_SILENCE_THRESHOLD)
        return self._waveforms[sample.hash]


def detect_equivalences(
    connection: Connection, library_root: Path, *, sample_limit: int | None = None
) -> EquivalenceSummary:
    """Find and persist every equivalence-class link the current catalog's samples support.

    Reruns are idempotent: the relation repository upserts on the same (subject, reference,
    relation_type, method) identity, so recomputing the same pair only refreshes its confidence
    and evidence rather than duplicating the row. The whole pass runs as one transaction so an
    interrupted run leaves nothing committed, rather than a partial set of relations a fresh rerun
    could then collide with -- DuckDB's own sequence-generated ids are not guaranteed to reflect
    every value already handed out once a connection ends without a clean commit.

    ``sample_limit``, when given, considers only that many catalogued samples -- a full pass over
    a real library is a batch job measured in tens of minutes, so this gives a quick way to
    validate a run over a small slice before committing to the whole catalog. Detection is
    expected to run repeatedly as the catalog itself grows, so leaving some pairs undetected in
    any one pass is an accepted, ordinary outcome, not a defect to guard against here.
    """
    sample_repository: SampleRepository = DuckDBSampleRepository(connection)
    relation_repository: SampleRelationRepository = DuckDBSampleRelationRepository(connection)
    samples = sample_repository.list_all()
    if sample_limit is not None:
        samples = samples[:sample_limit]
    waveforms = _WaveformCache(library_root)

    with start_batch(connection):
        bit_depth_relations, amplification_relations = _detect_gain_variants(relation_repository, samples, waveforms)

        fingerprints = {
            sample.hash: compute_fingerprint(waveforms.get(sample))
            for sample in tqdm(samples, desc="Fingerprinting samples")
        }
        resampled_relations = _detect_resampled_variants(relation_repository, samples, fingerprints, waveforms)

    return EquivalenceSummary(
        samples_considered=len(samples),
        bit_depth_relations=bit_depth_relations,
        amplification_relations=amplification_relations,
        resampled_relations=resampled_relations,
    )


def _detect_gain_variants(
    relation_repository: SampleRelationRepository, samples: tuple[Sample, ...], waveforms: _WaveformCache
) -> tuple[int, int]:
    """Detect and record every gain-compensated match, classified by whether depth changed with no
    audible gain change, or by anything else a gain-compensated match can mean.

    A single scorer and candidate space cover both kinds of match (see scoring.py's
    ``score_gain_variant``); depth is the fact that decides between them, not gain alone, since gain
    landing near 1.0 no longer implies depth changed once trailing-silence-trimmed pairs of equal
    depth are candidates too. A pair changing both depth and gain at once, and a pair whose only
    difference is a trimmed silent tail, are both classified as amplification variants -- the former
    carrying its own depth-changed evidence, mirroring how a resampled variant already records its
    own; the latter is a loose fit for that label, but a closer one than misreporting a depth change
    that never happened.
    """
    bit_depth_relations = 0
    amplification_relations = 0
    for pair in tqdm(gain_variant_candidate_pairs(samples), desc="Gain variants"):
        score = score_gain_variant(
            waveforms.get(pair[0]), waveforms.get(pair[1]), depth_a=pair[0].depth, depth_b=pair[1].depth
        )
        if score is None or score.confidence < GAIN_VARIANT_MINIMUM_CONFIDENCE:
            continue

        depth_changed = pair[0].depth is not pair[1].depth
        if depth_changed and abs(score.evidence["gain"] - 1.0) <= GAIN_UNITY_TOLERANCE:
            _record_relation(relation_repository, pair, RelationType.BIT_DEPTH_VARIANT, BIT_DEPTH_METHOD, score)
            bit_depth_relations += 1
        else:
            evidence = {**score.evidence, "depth_changed": 1.0 if depth_changed else 0.0}
            _record_relation(
                relation_repository,
                pair,
                RelationType.AMPLIFICATION_VARIANT,
                AMPLIFICATION_METHOD,
                RelationScore(confidence=score.confidence, evidence=evidence),
            )
            amplification_relations += 1

    return bit_depth_relations, amplification_relations


def _detect_resampled_variants(
    relation_repository: SampleRelationRepository,
    samples: tuple[Sample, ...],
    fingerprints: dict[str, NDArray[np.float64]],
    waveforms: _WaveformCache,
) -> int:
    relations_recorded = 0
    for pair in tqdm(resampled_candidate_pairs(samples, fingerprints), desc="Resampled variants"):
        score = score_resampled_variant(waveforms.get(pair[0]), waveforms.get(pair[1]))
        if score is None or score.confidence < RESAMPLED_MINIMUM_CONFIDENCE:
            continue

        evidence = {**score.evidence, "depth_changed": 1.0 if pair[0].depth is not pair[1].depth else 0.0}
        _record_relation(
            relation_repository,
            pair,
            RelationType.RESAMPLED_VARIANT,
            RESAMPLED_METHOD,
            RelationScore(confidence=score.confidence, evidence=evidence),
        )
        relations_recorded += 1

    return relations_recorded


def _record_relation(
    relation_repository: SampleRelationRepository,
    pair: tuple[Sample, Sample],
    relation_type: RelationType,
    method: str,
    score: RelationScore,
) -> None:
    subject_hash, reference_hash = sorted((pair[0].hash, pair[1].hash))
    relation_repository.upsert(
        SampleRelation(
            id=relation_repository.next_id(),
            subject_hash=subject_hash,
            reference_hash=reference_hash,
            relation_type=relation_type,
            method=method,
            confidence=score.confidence,
            evidence=score.evidence,
            detected_at=datetime.now(UTC),
        )
    )
