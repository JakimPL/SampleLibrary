from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection
from tqdm import tqdm

from samplecloud.backends import FeatureExtractor
from samplecloud.evaluation.corpus import EvaluationCorpus
from samplecloud.evaluation.settings import EvaluationSettings
from samplecore.storage import audio_store
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.waveform import resample_by_semitones

QUERY_CHUNK_SIZE: Final[int] = 64
CLOSE_RANK: Final[int] = 5


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
    both score zero at rank one, and they are not the same descriptor.
    """

    offsets: tuple[OffsetRetrieval, ...]
    probe_sample_count: int
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


def transposition_retrieval(
    connection: Connection,
    corpus: EvaluationCorpus,
    *,
    library_root: Path,
    feature_extractor: FeatureExtractor,
    settings: EvaluationSettings,
) -> TranspositionRetrieval:
    """Retune each probe sample by every offset and ask where its own original ranks.

    Raises:
        ValueError: the corpus holds no samples the probe can be drawn from.
    """
    if corpus.sample_count == 0:
        raise ValueError("an empty corpus offers no samples to retune")

    offsets = settings.semitone_offsets
    positions = _probe_positions(corpus, settings=settings)
    samples = PostgresSampleRepository(connection).get_many([corpus.sample_hashes[position] for position in positions])
    ranks_by_offset: dict[float, list[int]] = {offset: [] for offset in offsets}
    queries: list[NDArray[np.float64]] = []
    targets: list[int] = []
    query_offsets: list[float] = []
    for position in tqdm(positions, desc="Retuning probes"):
        sample = samples.get(corpus.sample_hashes[position])
        if sample is None:
            continue

        waveform = audio_store.read(library_root, sample).pcm
        for offset in offsets:
            retuned = resample_by_semitones(waveform, semitones=offset)
            queries.append(np.asarray(feature_extractor.extract(retuned), dtype=np.float64))
            targets.append(position)
            query_offsets.append(offset)

    for rank, offset in zip(_ranks_of(corpus, np.stack(queries), targets), query_offsets, strict=True):
        ranks_by_offset[offset].append(rank)

    return TranspositionRetrieval(
        offsets=tuple(_summarize(offset, ranks_by_offset[offset]) for offset in offsets),
        probe_sample_count=len(positions),
        catalog_sample_count=corpus.sample_count,
        random_seed=settings.random_seed,
    )


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
