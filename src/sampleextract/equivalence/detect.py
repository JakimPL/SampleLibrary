from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import Connection

from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.process_pool import IN_PROCESS_WORKERS, Mapper, worker_pool
from samplecore.progress import ProgressBar
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.fingerprint import PostgresSampleFingerprintRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio
from sampleextract.equivalence.candidates import NEIGHBOR_BLOCK_ROWS, Fingerprints, candidate_blocks
from sampleextract.equivalence.fingerprinting import comparison_layouts, fingerprint_samples
from sampleextract.equivalence.pairs import FoundRelation, PairBatch, PairScorer, ScoredBatch, pair_batches

# Moves whenever a change to the candidates, the scorers or their thresholds would judge any pair
# differently, so every sample is compared anew under the new rule.
COMPARISON_VERSION: Final[int] = 1
WAVEFORM_CACHE_BYTES: Final[int] = 1 << 30
COMPARING_LABEL: Final[str] = "Comparing samples"
PAIR_BATCH_CHUNK_SIZE: Final[int] = 1


@dataclass(frozen=True)
class EquivalenceSummary:
    """What one equivalence-detection pass did, across every sample it considered.

    ``silent_samples`` counts the samples holding nothing above the silence threshold, which have no
    content for a relation to be about. ``unavailable_samples`` counts the samples whose audio lives
    only in sample files none of which holds it now, and ``unavailable_pairs`` the candidate pairs
    left unscored because such a file went missing while the pass ran; a later pass takes them up.
    The candidates and the relations count what this pass compared: every pair reaching a sample no
    earlier pass compared.
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
class _Tally:
    unavailable_pairs: int = 0
    gain_candidates: int = 0
    resampled_candidates: int = 0
    bit_depth_relations: int = 0
    amplification_relations: int = 0
    resampled_relations: int = 0

    def count(self, relation_type: RelationType) -> None:
        match relation_type:
            case RelationType.BIT_DEPTH_VARIANT:
                self.bit_depth_relations += 1
            case RelationType.AMPLIFICATION_VARIANT:
                self.amplification_relations += 1
            case RelationType.RESAMPLED_VARIANT:
                self.resampled_relations += 1


@dataclass(frozen=True)
class _SubmittedBlock:
    """A block whose pairs the workers are scoring: its rows among the pass's samples, and the results as they come back."""

    rows: range
    gain_candidates: int
    resampled_candidates: int
    results: Iterator[ScoredBatch]


def detect_equivalences(
    connection: Connection, audio: SampleAudio, *, sample_limit: int | None = None, workers: int = IN_PROCESS_WORKERS
) -> EquivalenceSummary:
    """Find and persist every equivalence-class link the current catalog's samples support.

    Every sample is fingerprinted once, the fingerprints the catalog lacks read over ``workers``
    processes, or in this one where it names none. The candidate pairs then come block by block out
    of a search over those fingerprints (see ``candidate_blocks``), reaching only the samples no
    earlier pass compared under the current `COMPARISON_VERSION`: a pair of two compared samples
    was scored when the later of them was new. The workers score one block while this process
    searches the next, and each block's relations are committed together with its samples' mark of
    having been compared, so an interrupted pass keeps every block it finished, a rerun takes up the
    samples after them, and a catalog that grew compares only its new samples. A sample one of whose
    pairs could not be read stays unmarked, so a later pass compares it again. Reruns are idempotent:
    the relation repository upserts on the same (subject, reference, relation_type, method)
    identity, so recomputing the same pair only refreshes its confidence and evidence rather than
    duplicating the row.

    ``sample_limit``, when given, considers only the first that many cataloged samples in hash order,
    a quick way to validate a run over a small slice before committing to the whole catalog.

    Raises:
        ValueError: ``sample_limit`` is negative.
    """
    if sample_limit is not None and sample_limit < 0:
        raise ValueError(f"a sample limit counts samples, so it is at least 0, got {sample_limit}")

    samples = PostgresSampleRepository(connection).list_all()
    if sample_limit is not None:
        samples = samples[:sample_limit]
    fingerprinted = fingerprint_samples(connection, samples, audio, workers=workers)
    layouts = comparison_layouts(samples, fingerprinted, comparison_version=COMPARISON_VERSION)
    tally = _Tally()
    if layouts:
        _compare(connection, layouts, audio, workers=workers, tally=tally)

    return EquivalenceSummary(
        samples_considered=len(samples),
        silent_samples=fingerprinted.silent,
        unavailable_samples=fingerprinted.unavailable,
        unavailable_pairs=tally.unavailable_pairs,
        gain_candidates=tally.gain_candidates,
        resampled_candidates=tally.resampled_candidates,
        bit_depth_relations=tally.bit_depth_relations,
        amplification_relations=tally.amplification_relations,
        resampled_relations=tally.resampled_relations,
    )


def _compare(
    connection: Connection, layouts: tuple[Fingerprints, ...], audio: SampleAudio, *, workers: int, tally: _Tally
) -> None:
    """Compare every layout's new samples over one pool of ``workers`` processes.

    The pool scores pairs between the samples of every layout, laid one after another, so a pass
    starts its processes once. Each process holds its share of `WAVEFORM_CACHE_BYTES`, so the pass
    holds the same amount of audio however many processes score.
    """
    samples = tuple(sample for fingerprints in layouts for sample in fingerprints.samples)
    scorer = PairScorer(audio, samples=samples, cache_bytes=WAVEFORM_CACHE_BYTES // max(workers, 1))
    rows = len(samples)
    compared = sum(fingerprints.first_new for fingerprints in layouts)
    with (
        ProgressBar(total=rows, label=COMPARING_LABEL, resumed=compared) as progress,
        worker_pool(scorer, worker_count=workers) as mapper,
    ):
        comparison = _Comparison(connection=connection, samples=samples, mapper=mapper, progress=progress, tally=tally)
        first_row = 0
        for fingerprints in layouts:
            comparison.layout(fingerprints, first_row=first_row)
            first_row += len(fingerprints.samples)


@dataclass(frozen=True)
class _Comparison:
    """One pass comparing its new samples: the catalog it writes to, the samples of every layout, and its workers."""

    connection: Connection
    samples: tuple[Sample, ...]
    mapper: Mapper[PairBatch, ScoredBatch]
    progress: ProgressBar
    tally: _Tally

    def layout(self, fingerprints: Fingerprints, *, first_row: int) -> None:
        """Score every block of one layout's new rows, searching each next block while the workers score the one before.

        The layout's rows start at `first_row` among the pass's samples.
        """
        waiting: _SubmittedBlock | None = None
        for block in candidate_blocks(fingerprints, block_rows=NEIGHBOR_BLOCK_ROWS):
            submitted = _SubmittedBlock(
                rows=range(first_row + block.rows.start, first_row + block.rows.stop),
                gain_candidates=len(block.gain_pairs),
                resampled_candidates=len(block.resampled_pairs),
                results=self.mapper.map(pair_batches(block, first_row=first_row), chunk_size=PAIR_BATCH_CHUNK_SIZE),
            )
            if waiting is not None:
                self._record(waiting)
            waiting = submitted
        if waiting is not None:
            self._record(waiting)

    def _record(self, submitted: _SubmittedBlock) -> None:
        """Write one block's relations and mark its samples compared, in one transaction.

        A sample one of whose pairs could not be read is left unmarked, so a later pass compares it again.
        """
        scored = list(submitted.results)
        self.tally.gain_candidates += submitted.gain_candidates
        self.tally.resampled_candidates += submitted.resampled_candidates
        unfinished = {batch.owner for batch in scored if batch.unavailable_pairs > 0}
        self.tally.unavailable_pairs += sum(batch.unavailable_pairs for batch in scored)
        relations = PostgresSampleRelationRepository(self.connection)
        with start_batch(self.connection):
            for batch in scored:
                for found in batch.found:
                    _record_relation(relations, self.samples, found)
                    self.tally.count(found.relation_type)
            PostgresSampleFingerprintRepository(self.connection).mark_compared(
                (self.samples[row].hash for row in submitted.rows if row not in unfinished),
                comparison_version=COMPARISON_VERSION,
            )
        self.progress.update(len(submitted.rows))


def _record_relation(
    relations: PostgresSampleRelationRepository, samples: tuple[Sample, ...], found: FoundRelation
) -> None:
    subject_hash, reference_hash = sorted((samples[found.rows[0]].hash, samples[found.rows[1]].hash))
    relations.upsert(
        SampleRelation(
            id=relations.next_id(),
            subject_hash=subject_hash,
            reference_hash=reference_hash,
            relation_type=found.relation_type,
            method=found.method,
            confidence=found.score.confidence,
            evidence=found.score.evidence,
            detected_at=datetime.now(UTC),
        )
    )
