from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.models.relation import RelationType
from samplecore.models.sample import Sample
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplecore.waveform import trim_trailing_silence
from sampleextract.equivalence.candidates import CandidateBlock
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

PairRows = tuple[int, int]


@unique
class PairKind(StrEnum):
    """Which scorer a candidate pair goes to: the gain fit, or the resampled correlation."""

    GAIN = "gain"
    RESAMPLED = "resampled"


@dataclass(frozen=True)
class PairBatch:
    """The candidate pairs of one kind a new row found, scored together so that row's waveform is read once."""

    kind: PairKind
    owner: int
    pairs: tuple[PairRows, ...]


@dataclass(frozen=True)
class FoundRelation:
    """A relation a scored pair holds, between the samples of two rows, the lower hash first."""

    rows: PairRows
    relation_type: RelationType
    method: str
    score: RelationScore


@dataclass(frozen=True)
class ScoredBatch:
    """What scoring one batch found, and how many of its pairs could not be read."""

    owner: int
    found: tuple[FoundRelation, ...]
    unavailable_pairs: int


@dataclass
class WaveformCache:
    """Reads a Sample's trailing-silence-trimmed waveform once while the pairs it joins are scored.

    Trimming here, rather than in each scorer, means every detector compares the same trimmed
    content, the content the candidates' fingerprints were read from. The cache keeps the waveforms read
    most recently, up to ``byte_budget``: candidate pairs arrive grouped by the row that found them,
    so the one waveform most pairs share stays on hand while a pass over a whole catalog holds a
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


class PairScorer:
    """Scores batches of candidate pairs between the samples of one layout's rows, sent once to every worker process.

    Each process keeps its own `WaveformCache` of `cache_bytes`, filled as it scores, so the
    batches a process meets in turn share the waveforms it read for the ones before.
    """

    def __init__(self, audio: SampleAudio, *, samples: tuple[Sample, ...], cache_bytes: int) -> None:
        self._samples = samples
        self._waveforms = WaveformCache(audio, byte_budget=cache_bytes)

    def __call__(self, batch: PairBatch) -> ScoredBatch:
        found: list[FoundRelation] = []
        unavailable_pairs = 0
        for rows in batch.pairs:
            pair = (self._samples[rows[0]], self._samples[rows[1]])
            try:
                waveforms = (self._waveforms.get(pair[0]), self._waveforms.get(pair[1]))
            except SampleUnavailableError:
                unavailable_pairs += 1
                continue
            relation = _scored(batch.kind, rows, pair, waveforms)
            if relation is not None:
                found.append(relation)
        return ScoredBatch(owner=batch.owner, found=tuple(found), unavailable_pairs=unavailable_pairs)


def pair_batches(block: CandidateBlock, *, first_row: int) -> tuple[PairBatch, ...]:
    """A block's candidate pairs, batched by the new row that found them and by kind, their rows moved by `first_row`.

    The row that found a pair is the later of its two, the one inside the block. A pass laying
    several layouts' samples one after another moves each layout's rows to where its samples start.
    """
    batches: list[PairBatch] = []
    for kind, pairs in ((PairKind.GAIN, block.gain_pairs), (PairKind.RESAMPLED, block.resampled_pairs)):
        by_owner: dict[int, list[PairRows]] = {}
        for first, second in pairs:
            by_owner.setdefault(first_row + max(first, second), []).append((first_row + first, first_row + second))
        batches.extend(PairBatch(kind=kind, owner=owner, pairs=tuple(rows)) for owner, rows in by_owner.items())
    return tuple(batches)


def _scored(
    kind: PairKind,
    rows: PairRows,
    pair: tuple[Sample, Sample],
    waveforms: tuple[NDArray[np.float64], NDArray[np.float64]],
) -> FoundRelation | None:
    match kind:
        case PairKind.GAIN:
            return _gain_relation(rows, pair, waveforms)
        case PairKind.RESAMPLED:
            return _resampled_relation(rows, pair, waveforms)


def _gain_relation(
    rows: PairRows, pair: tuple[Sample, Sample], waveforms: tuple[NDArray[np.float64], NDArray[np.float64]]
) -> FoundRelation | None:
    """Score one gain candidate, classified by whether depth changed with no audible gain change.

    A single scorer covers both kinds of match (see scoring.py's ``score_gain_variant``); depth is
    the fact that decides between them, not gain alone, since gain landing near 1.0 no longer
    implies depth changed once trailing-silence-trimmed pairs of equal depth are candidates too. A
    pair changing both depth and gain at once, and a pair whose only difference is a trimmed silent
    tail, are both classified as amplification variants -- the former carrying its own depth-changed
    evidence, mirroring how a resampled variant already records its own.
    """
    score = score_gain_variant(*waveforms, depth_a=pair[0].depth, depth_b=pair[1].depth)
    if score is None or score.confidence < GAIN_VARIANT_MINIMUM_CONFIDENCE:
        return None

    depth_changed = pair[0].depth is not pair[1].depth
    if depth_changed and abs(score.evidence["gain"] - 1.0) <= GAIN_UNITY_TOLERANCE:
        return FoundRelation(
            rows=rows, relation_type=RelationType.BIT_DEPTH_VARIANT, method=BIT_DEPTH_METHOD, score=score
        )

    evidence = {**score.evidence, "depth_changed": 1.0 if depth_changed else 0.0}
    return FoundRelation(
        rows=rows,
        relation_type=RelationType.AMPLIFICATION_VARIANT,
        method=AMPLIFICATION_METHOD,
        score=RelationScore(confidence=score.confidence, evidence=evidence),
    )


def _resampled_relation(
    rows: PairRows, pair: tuple[Sample, Sample], waveforms: tuple[NDArray[np.float64], NDArray[np.float64]]
) -> FoundRelation | None:
    score = score_resampled_variant(*waveforms)
    if score is None or score.confidence < RESAMPLED_MINIMUM_CONFIDENCE:
        return None

    evidence = {**score.evidence, "depth_changed": 1.0 if pair[0].depth is not pair[1].depth else 0.0}
    return FoundRelation(
        rows=rows,
        relation_type=RelationType.RESAMPLED_VARIANT,
        method=RESAMPLED_METHOD,
        score=RelationScore(confidence=score.confidence, evidence=evidence),
    )
