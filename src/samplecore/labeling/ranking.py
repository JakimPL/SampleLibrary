from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from samplecore.labeling.labels import SampleLabel, label_agreement


def agreement_matrix(labels: Sequence[SampleLabel]) -> NDArray[np.float64]:
    """Pairwise label agreement, with nothing on the diagonal."""
    agreements = np.zeros((len(labels), len(labels)), dtype=np.float64)
    for first, first_label in enumerate(labels):
        for second in range(first + 1, len(labels)):
            agreements[first, second] = agreements[second, first] = label_agreement(first_label, labels[second])
    return agreements


def nearest_first(vectors: NDArray[np.floating], *, groups: NDArray[np.int64]) -> NDArray[np.int64]:
    """Each row's other rows, nearest first, with itself and its own group marked -1 at the end.

    A row's own group is left out so a near-duplicate can never stand in for a genuine neighbor,
    which is the same rule every split in the evaluation harness follows.
    """
    values = np.asarray(vectors, dtype=np.float64)
    squared_norms = (values**2).sum(axis=1)
    distances = squared_norms[:, None] - 2.0 * values @ values.T + squared_norms[None, :]
    excluded = groups[:, None] == groups[None, :]
    distances[excluded] = np.inf
    order = np.argsort(distances, axis=1, kind="stable")
    ranking = np.where(np.take_along_axis(excluded, order, axis=1), -1, order)
    return ranking[:, : values.shape[0] - 1] if values.shape[0] > 1 else ranking[:, :0]


def ndcg_per_query(
    agreements: NDArray[np.float64], ranking: NDArray[np.int64], *, neighborhood: int
) -> NDArray[np.float64]:
    """Graded gain over each query's nearest `neighborhood`, against its best possible ordering.

    The gain of a neighbor is its agreement with the query, discounted by its rank, so finding a
    closed hi-hat next to an open one earns part of what a closed one would. A query whose
    candidates agree with it nowhere has nothing to find and reads as NaN.
    """
    count = ranking.shape[0]
    nearest = ranking[:, :neighborhood]
    rows = np.arange(count)[:, None]
    gains = np.where(nearest >= 0, agreements[rows, np.maximum(nearest, 0)], 0.0)
    discounts = 1.0 / np.log2(np.arange(2, nearest.shape[1] + 2))
    reached = (gains * discounts).sum(axis=1)
    every_gain = np.where(ranking >= 0, agreements[rows, np.maximum(ranking, 0)], 0.0)
    ideal = (-np.sort(-every_gain)[:, : nearest.shape[1]] * discounts).sum(axis=1)
    return np.where(ideal > 0.0, reached / np.where(ideal > 0.0, ideal, 1.0), np.nan)
