from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, unique
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecloud.backends import FeatureExtractor
from samplecloud.evaluation.corpus import EvaluationCorpus
from samplecloud.evaluation.settings import EvaluationSettings
from samplecloud.evaluation.stages import PROBE_STATUS_FILE_NAME, QUERIES_FILE_NAME, EvaluationStages
from samplecloud.hearing import Hearing
from samplecore.models.sample import Sample
from samplecore.progress import ProgressBar
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplecore.storage.staged_rows import StagedRows
from samplecore.waveform import resample_by_semitones

QUERY_CHUNK_SIZE: Final[int] = 64
CLOSE_RANK: Final[int] = 5
RETUNING_LABEL: Final[str] = "Retuning probes"


@dataclass(frozen=True)
class OffsetRetrieval:
    """How a descriptor found the original when its sample was retuned by one offset."""

    semitone_offset: float
    trial_count: int
    rank_one_share: float
    close_rank_share: float
    median_rank: float


@dataclass(frozen=True)
class TranspositionRetrieval:
    """Whether a descriptor still recognizes a sample once it is played at a different pitch.

    This is the property the whole representation is built for, and the only one measurable without
    any label at all: retuning a waveform produces a sample the catalog holds an answer for, so the
    rank the original lands at says directly how far pitch moves a descriptor.

    The offsets form a fixed mirrored grid rather than a random draw, so two runs compare directly
    and each offset's own difficulty stays visible. `median_rank` sits beside the shares because a
    descriptor placing the original second every time and one placing it forty-thousandth every time
    both score zero at rank one, and they are not the same descriptor. `unavailable_probe_count`
    counts the drawn probes whose sample files are gone, which the trials leave out.
    """

    offsets: tuple[OffsetRetrieval, ...]
    probe_sample_count: int
    unavailable_probe_count: int
    catalog_sample_count: int
    random_seed: int

    @property
    def rank_one_share(self) -> float:
        """The share of every trial, over all offsets, that put the original first."""
        return float(np.mean([offset.rank_one_share for offset in self.offsets])) if self.offsets else 0.0

    @property
    def median_rank(self) -> float:
        """The middle rank across offsets, which says what a typical retrieval looks like."""
        return float(np.median([offset.median_rank for offset in self.offsets])) if self.offsets else 0.0


@dataclass(frozen=True)
class ProbeDescriber:
    """What describes a retuned probe again: the experiment's own extractor, hearing samples its own way from the audio they are read from."""

    feature_extractor: FeatureExtractor
    hearing: Hearing
    audio: SampleAudio


@unique
class ProbeReading(IntEnum):
    """How reading one probe went, kept beside its vectors: described, gone from the catalog, or with no file to read."""

    GONE = 0
    DESCRIBED = 1
    UNAVAILABLE = 2


def transposition_retrieval(
    connection: Connection,
    corpus: EvaluationCorpus,
    *,
    describer: ProbeDescriber,
    settings: EvaluationSettings,
    stages: EvaluationStages,
) -> TranspositionRetrieval | None:
    """Retune each probe sample by every offset and ask where its own original ranks.

    Each probe is heard the way the experiment heard its samples before it is retuned, so an
    unretuned probe is described exactly as its stored vector was. A probe's retunings are described
    together and kept among the pass's `stages` as they come, so a pass stopped partway takes up with
    the next probe. A probe whose sample files are gone is counted and left out. Returns None when
    the corpus offers no probe the catalog still holds and can read.
    """
    offsets = settings.semitone_offsets
    positions = _probe_positions(corpus, settings=settings)
    rows = stages.probe_rows(probe_count=len(positions), offset_count=len(offsets), dimensions=corpus.vectors.shape[1])
    samples = PostgresSampleRepository(connection).get_many([corpus.sample_hashes[position] for position in positions])
    probes = tuple(samples.get(corpus.sample_hashes[position]) for position in positions)
    _describe_probes(probes, rows=rows, describer=describer, offsets=offsets)
    readings = rows.array(PROBE_STATUS_FILE_NAME)
    described = np.flatnonzero(readings == ProbeReading.DESCRIBED)
    if described.size == 0:
        return None

    queries = np.asarray(rows.array(QUERIES_FILE_NAME)[described]).reshape(-1, corpus.vectors.shape[1])
    targets = np.repeat(positions[described], len(offsets)).tolist()
    ranks_by_offset: dict[float, list[int]] = {offset: [] for offset in offsets}
    for rank, offset in zip(_ranks_of(corpus, queries, targets), offsets * int(described.size), strict=True):
        ranks_by_offset[offset].append(rank)

    return TranspositionRetrieval(
        offsets=tuple(_summarize(offset, ranks_by_offset[offset]) for offset in offsets),
        probe_sample_count=len(positions),
        unavailable_probe_count=int((readings == ProbeReading.UNAVAILABLE).sum()),
        catalog_sample_count=corpus.sample_count,
        random_seed=settings.random_seed,
    )


def _describe_probes(
    probes: tuple[Sample | None, ...], *, rows: StagedRows, describer: ProbeDescriber, offsets: tuple[float, ...]
) -> None:
    """Describe every probe a stopped pass left undescribed, checkpointing as they come and on the way out.

    `probes` holds each probe's sample, or ``None`` for one the catalog no longer holds.
    """
    queries = rows.array(QUERIES_FILE_NAME)
    readings = rows.array(PROBE_STATUS_FILE_NAME)
    with ProgressBar(total=len(probes), label=RETUNING_LABEL, resumed=rows.resumed_rows) as progress:
        try:
            for row in range(rows.resumed_rows, len(probes)):
                reading = _probe_reading(probes[row], describer, offsets)
                if isinstance(reading, ProbeReading):
                    readings[row] = reading
                else:
                    queries[row] = reading
                    readings[row] = ProbeReading.DESCRIBED
                rows.advance_to(row + 1)
                progress.update(1)
        finally:
            rows.checkpoint()


def _probe_reading(
    sample: Sample | None, describer: ProbeDescriber, offsets: tuple[float, ...]
) -> NDArray[np.float64] | ProbeReading:
    """One probe's vector at every offset, `(offsets, dimensions)`, or why none was read."""
    if sample is None:
        return ProbeReading.GONE
    try:
        sample_pcm = describer.audio.read(sample)
    except SampleUnavailableError:
        return ProbeReading.UNAVAILABLE
    waveform = describer.hearing.hear(sample.hash, sample_pcm.pcm)
    retuned = [resample_by_semitones(waveform, semitones=offset) for offset in offsets]
    return np.stack(describer.feature_extractor.extract_many(retuned)).astype(np.float64)


def _probe_positions(corpus: EvaluationCorpus, *, settings: EvaluationSettings) -> NDArray[np.intp]:
    """Which corpus rows to retune, drawn once from a seed so two runs read the same samples."""
    generator = np.random.default_rng(settings.random_seed)
    probe_count = min(settings.probe_count, corpus.sample_count)
    return np.sort(generator.choice(corpus.sample_count, size=probe_count, replace=False))


def _ranks_of(corpus: EvaluationCorpus, queries: NDArray[np.float64], targets: list[int]) -> list[int]:
    """Where each query's own original sits when the whole catalog is ordered by distance to it.

    Counting how many samples sit closer than the target costs one pass and reports the same rank an
    ordering would, which keeps a whole-catalog search over thousands of queries within reach.
    """
    standardized = corpus.standardization.apply(queries)
    ranks: list[int] = []
    for chunk_start in range(0, standardized.shape[0], QUERY_CHUNK_SIZE):
        chunk = standardized[chunk_start : chunk_start + QUERY_CHUNK_SIZE]
        distances = _squared_distances(corpus.vectors, chunk)
        for column, target in enumerate(targets[chunk_start : chunk_start + QUERY_CHUNK_SIZE]):
            to_target = distances[target, column]
            ranks.append(int((distances[:, column] < to_target).sum()) + 1)
    return ranks


def _squared_distances(vectors: NDArray[np.float64], queries: NDArray[np.float64]) -> NDArray[np.float64]:
    """Squared distance from every catalog vector to every query, as a (catalog, query) grid."""
    catalog_lengths = (vectors**2).sum(axis=1)[:, None]
    query_lengths = (queries**2).sum(axis=1)[None, :]
    distances: NDArray[np.float64] = catalog_lengths - 2.0 * vectors @ queries.T + query_lengths
    return distances


def _summarize(offset: float, ranks: list[int]) -> OffsetRetrieval:
    found = np.array(ranks, dtype=np.float64)
    return OffsetRetrieval(
        semitone_offset=offset,
        trial_count=len(ranks),
        rank_one_share=float((found == 1).mean()) if ranks else 0.0,
        close_rank_share=float((found <= CLOSE_RANK).mean()) if ranks else 0.0,
        median_rank=float(np.median(found)) if ranks else 0.0,
    )
