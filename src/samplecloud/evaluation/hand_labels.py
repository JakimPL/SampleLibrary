from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecloud.evaluation.corpus import EvaluationCorpus
from samplecloud.evaluation.settings import EvaluationSettings
from samplecore.labeling.labels import LabelPath, SampleLabel, format_path
from samplecore.labeling.ranking import agreement_matrix, ndcg_per_query, nearest_first

MINIMUM_LABELED_SAMPLES: Final[int] = 10
MINIMUM_TAG_SUPPORT: Final[int] = 5
NEIGHBORHOOD_SIZE: Final[int] = 10
BOOTSTRAP_DRAWS: Final[int] = 1000
CHANCE_DRAWS: Final[int] = 20
INTERVAL_SHARE: Final[float] = 0.9


@dataclass(frozen=True)
class TagScore:
    """How well one tag's samples find each other, beside how many carry it."""

    path: str
    average_precision: float
    support: int


@dataclass(frozen=True)
class HandLabelAgreement:
    """Whether a descriptor puts samples a person labeled alike near one another.

    Each labeled sample looks up its nearest labeled neighbors and is credited by how much their
    labels agree with its own, graded along the hierarchy, so a closed hi-hat found next to an open
    one earns part of the credit a closed one would. `ndcg` reads the whole neighborhood that way,
    `precision_at_one` asks only whether the nearest neighbor shares any tag, and `per_tag` scores
    every tag with enough support on its own, which is how a treatment such as lo-fi is judged
    apart from a source such as snare.

    The labeled set is small and grows as the person labels, so `ndcg` carries a bootstrap interval
    over the queries and every score its chance level, and `coverage` says what share of the catalog
    the score describes.
    """

    ndcg: float
    ndcg_interval: tuple[float, float]
    ndcg_chance: float
    mean_average_precision: float
    precision_at_one: float
    precision_at_one_chance: float
    coverage: float
    labeled_sample_count: int
    label_depth: int | None
    neighborhood_size: int
    per_tag: tuple[TagScore, ...]


@dataclass(frozen=True)
class _LabeledSubset:
    """The labeled samples' vectors, labels and equivalence groups, in one order."""

    labels: tuple[SampleLabel, ...]
    vectors: NDArray[np.float64]
    groups: NDArray[np.int64]

    @property
    def count(self) -> int:
        return len(self.labels)


def hand_label_agreement(corpus: EvaluationCorpus, *, settings: EvaluationSettings) -> HandLabelAgreement:
    """Score a descriptor against the hand labels, each labeled sample ranking every other.

    A sample's near-duplicates stay out of its ranking, for the same reason the other metrics split
    by equivalence class: finding a copy of oneself says nothing about the descriptor.

    Raises:
        ValueError: fewer than `MINIMUM_LABELED_SAMPLES` labeled samples carry a vector.
    """
    subset = _labeled_subset(corpus, depth=settings.label_depth)
    if subset.count < MINIMUM_LABELED_SAMPLES:
        raise ValueError(
            f"{subset.count} labeled samples carry a vector, and at least {MINIMUM_LABELED_SAMPLES} are needed"
        )

    agreements = agreement_matrix(subset.labels)
    ranking = nearest_first(subset.vectors, groups=subset.groups)
    per_query_ndcg = ndcg_per_query(agreements, ranking, neighborhood=NEIGHBORHOOD_SIZE)
    generator = np.random.default_rng(settings.random_seed)
    chance_ndcg = float(
        np.mean(
            [
                np.nanmean(ndcg_per_query(agreements, _shuffled(ranking, generator), neighborhood=NEIGHBORHOOD_SIZE))
                for _ in range(CHANCE_DRAWS)
            ]
        )
    )
    per_tag = _per_tag(subset, ranking)
    return HandLabelAgreement(
        ndcg=float(np.nanmean(per_query_ndcg)),
        ndcg_interval=_bootstrap_interval(per_query_ndcg, generator),
        ndcg_chance=chance_ndcg,
        mean_average_precision=float(np.mean([score.average_precision for score in per_tag])) if per_tag else 0.0,
        precision_at_one=_precision_at_one(agreements, ranking[:, :1]),
        precision_at_one_chance=_precision_at_one(agreements, ranking),
        coverage=subset.count / corpus.sample_count,
        labeled_sample_count=subset.count,
        label_depth=settings.label_depth,
        neighborhood_size=NEIGHBORHOOD_SIZE,
        per_tag=per_tag,
    )


def _labeled_subset(corpus: EvaluationCorpus, *, depth: int | None) -> _LabeledSubset:
    positions = np.flatnonzero(corpus.labeled)
    labels = []
    for position in positions:
        label = corpus.labels[position]
        if label is None:
            continue
        labels.append(label if depth is None else label.truncated(depth=depth))
    return _LabeledSubset(
        labels=tuple(labels),
        vectors=corpus.vectors[positions],
        groups=corpus.equivalence_groups[positions],
    )


def _precision_at_one(agreements: NDArray[np.float64], candidates: NDArray[np.int64]) -> float:
    """The share of the given candidate pairs sharing any tag; over the nearest alone it is precision at one."""
    rows = np.nonzero(candidates >= 0)[0]
    return float(np.mean(agreements[rows, candidates[candidates >= 0]] > 0.0)) if len(rows) else 0.0


def _shuffled(ranking: NDArray[np.int64], generator: np.random.Generator) -> NDArray[np.int64]:
    """The same candidates per query in a random order, which is what a descriptor knowing nothing yields."""
    shuffled = ranking.copy()
    for row in shuffled:
        candidates = row[row >= 0]
        row[: len(candidates)] = generator.permutation(candidates)
    return shuffled


def _bootstrap_interval(per_query: NDArray[np.float64], generator: np.random.Generator) -> tuple[float, float]:
    scored = per_query[~np.isnan(per_query)]
    draws = [float(scored[generator.integers(0, len(scored), len(scored))].mean()) for _ in range(BOOTSTRAP_DRAWS)]
    tail = (1.0 - INTERVAL_SHARE) / 2.0
    low, high = np.quantile(draws, [tail, 1.0 - tail])
    return float(low), float(high)


def _per_tag(subset: _LabeledSubset, ranking: NDArray[np.int64]) -> tuple[TagScore, ...]:
    """Average precision of finding a tag's other samples, for every tag with enough support."""
    members: dict[LabelPath, list[int]] = {}
    for position, label in enumerate(subset.labels):
        for path in label.closure:
            members.setdefault(path, []).append(position)

    scores = []
    for path, positions in sorted(members.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(positions) < MINIMUM_TAG_SUPPORT:
            continue
        is_member = np.zeros(subset.count, dtype=bool)
        is_member[positions] = True
        precisions = [_average_precision(is_member, ranking[query]) for query in positions]
        scored = [precision for precision in precisions if precision is not None]
        if scored:
            scores.append(
                TagScore(path=format_path(path), average_precision=float(np.mean(scored)), support=len(positions))
            )
    return tuple(scores)


def _average_precision(is_member: NDArray[np.bool_], ranked: NDArray[np.int64]) -> float | None:
    candidates = ranked[ranked >= 0]
    relevant = is_member[candidates]
    if not relevant.any():
        return None
    precision_at_rank = np.cumsum(relevant) / np.arange(1, len(relevant) + 1)
    return float((precision_at_rank * relevant).sum() / relevant.sum())
