from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.models.channels import ChannelLayout
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.progress import tracked
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository, SampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplecore.waveform import trim_trailing_silence
from sampleextract.equivalence.candidates import NEIGHBOR_BLOCK_ROWS, CandidateBlock, Fingerprints, candidate_blocks
from sampleextract.equivalence.fingerprint import FINGERPRINT_SIZE, compute_rate_fingerprint, compute_shape_fingerprint
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
WAVEFORM_CACHE_BYTES: Final[int] = 1 << 30


@dataclass(frozen=True)
class EquivalenceSummary:
    """What one equivalence-detection pass did, across every sample it considered.

    ``silent_samples`` counts the samples holding nothing above the silence threshold, which have no
    content for a relation to be about. ``unavailable_samples`` counts the samples whose audio lives
    only in sample files none of which holds it now, and ``unavailable_pairs`` the candidate pairs
    left unscored because such a file went missing while the pass ran; a later pass takes them up.
    """

    samples_considered: int
    silent_samples: int
    unavailable_samples: int
    unavailable_pairs: int
    gain_candidates: int
    resampled_candidates: int
    bit_depth_relations: int
    amplification_relations: int
    resampled_relations: int


@dataclass
class _WaveformCache:
    """Reads a Sample's trailing-silence-trimmed waveform once while the pairs it joins are scored.

    Trimming here, rather than in each scorer, means every detector -- and the fingerprints the
    candidates come from -- compares the same trimmed content. The cache keeps the waveforms read
    most recently, up to ``byte_budget``: candidate pairs arrive grouped by their first sample, so
    the one waveform most pairs share stays on hand while a pass over a whole catalog holds a
    bounded amount of audio.
    """

    audio: SampleAudio
    byte_budget: int
    _waveforms: OrderedDict[str, NDArray[np.float64]] = field(default_factory=OrderedDict)
    _held_bytes: int = 0

    def get(self, sample: Sample) -> NDArray[np.float64]:
        """A sample's trimmed waveform, read once while it stays among the most recent.

        Raises:
            SampleUnavailableError: the sample lives only in sample files, and none of them holds it now.
        """
        cached = self._waveforms.get(sample.hash)
        if cached is not None:
            self._waveforms.move_to_end(sample.hash)
            return cached

        pcm = self.audio.read(sample).pcm
        waveform = trim_trailing_silence(pcm, threshold=TRAILING_SILENCE_THRESHOLD)
        self._hold(sample.hash, waveform)
        return waveform

    def _hold(self, sample_hash: str, waveform: NDArray[np.float64]) -> None:
        if waveform.nbytes > self.byte_budget:
            return
        while self._held_bytes + waveform.nbytes > self.byte_budget:
            _, released = self._waveforms.popitem(last=False)
            self._held_bytes -= released.nbytes
        self._waveforms[sample_hash] = waveform
        self._held_bytes += waveform.nbytes


@dataclass(frozen=True)
class _Fingerprinted:
    sample: Sample
    shape: NDArray[np.float64]
    rate: NDArray[np.float64]
    trimmed_frames: int


@dataclass
class _Tally:
    silent_samples: int = 0
    unavailable_samples: int = 0
    unavailable_pairs: int = 0
    gain_candidates: int = 0
    resampled_candidates: int = 0
    bit_depth_relations: int = 0
    amplification_relations: int = 0
    resampled_relations: int = 0


def detect_equivalences(
    connection: Connection, audio: SampleAudio, *, sample_limit: int | None = None
) -> EquivalenceSummary:
    """Find and persist every equivalence-class link the current catalog's samples support.

    Every sample is fingerprinted first, one waveform at a time, and the candidate pairs then come
    block by block out of a search over those fingerprints (see ``candidate_blocks``). Each block's
    relations are committed as the block finishes, so an interrupted pass keeps what it found and a
    rerun takes up the rest. Reruns are idempotent: the relation repository upserts on the same
    (subject, reference, relation_type, method) identity, so recomputing the same pair only
    refreshes its confidence and evidence rather than duplicating the row.

    ``sample_limit``, when given, considers only the first that many cataloged samples in hash order,
    a quick way to validate a run over a small slice before committing to the whole catalog.
    Detection is expected to run repeatedly as the catalog itself grows, so leaving some pairs
    undetected in any one pass is an accepted, ordinary outcome, not a defect to guard against here.

    Raises:
        ValueError: ``sample_limit`` is negative.
    """
    if sample_limit is not None and sample_limit < 0:
        raise ValueError(f"a sample limit counts samples, so it is at least 0, got {sample_limit}")

    samples = PostgresSampleRepository(connection).list_all()
    if sample_limit is not None:
        samples = samples[:sample_limit]
    relation_repository = PostgresSampleRelationRepository(connection)
    waveforms = _WaveformCache(audio, byte_budget=WAVEFORM_CACHE_BYTES)
    tally = _Tally()

    for fingerprints in _fingerprints_by_layout(samples, waveforms, tally=tally):
        blocks = candidate_blocks(fingerprints, block_rows=NEIGHBOR_BLOCK_ROWS)
        block_count = -(-len(fingerprints.samples) // NEIGHBOR_BLOCK_ROWS)
        for block in tracked(blocks, total=block_count, label="Scoring candidate blocks"):
            with start_batch(connection):
                _record_block(relation_repository, block, waveforms, tally=tally)

    return EquivalenceSummary(
        samples_considered=len(samples),
        silent_samples=tally.silent_samples,
        unavailable_samples=tally.unavailable_samples,
        unavailable_pairs=tally.unavailable_pairs,
        gain_candidates=tally.gain_candidates,
        resampled_candidates=tally.resampled_candidates,
        bit_depth_relations=tally.bit_depth_relations,
        amplification_relations=tally.amplification_relations,
        resampled_relations=tally.resampled_relations,
    )


def _fingerprints_by_layout(
    samples: tuple[Sample, ...], waveforms: _WaveformCache, *, tally: _Tally
) -> tuple[Fingerprints, ...]:
    """Every sample holding sound that can be read now, fingerprinted and grouped by channel layout, which relations never cross."""
    kept: dict[ChannelLayout, list[_Fingerprinted]] = {layout: [] for layout in ChannelLayout}
    for sample in tracked(samples, total=len(samples), label="Fingerprinting samples"):
        try:
            waveform = waveforms.get(sample)
        except SampleUnavailableError:
            tally.unavailable_samples += 1
            continue
        if waveform.shape[0] == 0:
            tally.silent_samples += 1
            continue
        kept[sample.channels].append(
            _Fingerprinted(
                sample=sample,
                shape=compute_shape_fingerprint(waveform),
                rate=compute_rate_fingerprint(waveform),
                trimmed_frames=waveform.shape[0],
            )
        )

    return tuple(
        Fingerprints(
            samples=tuple(row.sample for row in rows),
            shapes=np.array([row.shape for row in rows], dtype=np.float32).reshape(-1, FINGERPRINT_SIZE),
            rates=np.array([row.rate for row in rows], dtype=np.float32).reshape(-1, FINGERPRINT_SIZE),
            trimmed_frames=np.array([row.trimmed_frames for row in rows], dtype=np.int64),
        )
        for rows in kept.values()
        if rows
    )


def _record_block(
    relation_repository: SampleRelationRepository, block: CandidateBlock, waveforms: _WaveformCache, *, tally: _Tally
) -> None:
    tally.gain_candidates += len(block.gain_pairs)
    tally.resampled_candidates += len(block.resampled_pairs)
    for pair in block.gain_pairs:
        pair_waveforms = _pair_waveforms(pair, waveforms, tally=tally)
        if pair_waveforms is not None:
            _record_gain_variant(relation_repository, pair, pair_waveforms, tally=tally)
    for pair in block.resampled_pairs:
        pair_waveforms = _pair_waveforms(pair, waveforms, tally=tally)
        if pair_waveforms is not None:
            _record_resampled_variant(relation_repository, pair, pair_waveforms, tally=tally)


def _pair_waveforms(
    pair: tuple[Sample, Sample], waveforms: _WaveformCache, *, tally: _Tally
) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
    """Both waveforms of a candidate pair, or ``None`` counted as unavailable when a file went missing since fingerprinting."""
    try:
        return waveforms.get(pair[0]), waveforms.get(pair[1])
    except SampleUnavailableError:
        tally.unavailable_pairs += 1
        return None


def _record_gain_variant(
    relation_repository: SampleRelationRepository,
    pair: tuple[Sample, Sample],
    pair_waveforms: tuple[NDArray[np.float64], NDArray[np.float64]],
    *,
    tally: _Tally,
) -> None:
    """Score one gain candidate and record it, classified by whether depth changed with no audible gain change.

    A single scorer covers both kinds of match (see scoring.py's ``score_gain_variant``); depth is
    the fact that decides between them, not gain alone, since gain landing near 1.0 no longer
    implies depth changed once trailing-silence-trimmed pairs of equal depth are candidates too. A
    pair changing both depth and gain at once, and a pair whose only difference is a trimmed silent
    tail, are both classified as amplification variants -- the former carrying its own depth-changed
    evidence, mirroring how a resampled variant already records its own.
    """
    score = score_gain_variant(*pair_waveforms, depth_a=pair[0].depth, depth_b=pair[1].depth)
    if score is None or score.confidence < GAIN_VARIANT_MINIMUM_CONFIDENCE:
        return

    depth_changed = pair[0].depth is not pair[1].depth
    if depth_changed and abs(score.evidence["gain"] - 1.0) <= GAIN_UNITY_TOLERANCE:
        _record_relation(relation_repository, pair, RelationType.BIT_DEPTH_VARIANT, BIT_DEPTH_METHOD, score)
        tally.bit_depth_relations += 1
        return

    evidence = {**score.evidence, "depth_changed": 1.0 if depth_changed else 0.0}
    _record_relation(
        relation_repository,
        pair,
        RelationType.AMPLIFICATION_VARIANT,
        AMPLIFICATION_METHOD,
        RelationScore(confidence=score.confidence, evidence=evidence),
    )
    tally.amplification_relations += 1


def _record_resampled_variant(
    relation_repository: SampleRelationRepository,
    pair: tuple[Sample, Sample],
    pair_waveforms: tuple[NDArray[np.float64], NDArray[np.float64]],
    *,
    tally: _Tally,
) -> None:
    score = score_resampled_variant(*pair_waveforms)
    if score is None or score.confidence < RESAMPLED_MINIMUM_CONFIDENCE:
        return

    evidence = {**score.evidence, "depth_changed": 1.0 if pair[0].depth is not pair[1].depth else 0.0}
    _record_relation(
        relation_repository,
        pair,
        RelationType.RESAMPLED_VARIANT,
        RESAMPLED_METHOD,
        RelationScore(confidence=score.confidence, evidence=evidence),
    )
    tally.resampled_relations += 1


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
