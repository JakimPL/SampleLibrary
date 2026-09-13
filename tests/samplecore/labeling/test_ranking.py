from __future__ import annotations

import numpy as np

from samplecore.labeling.labels import SampleLabel
from samplecore.labeling.ranking import agreement_matrix, ndcg_per_query, nearest_first


def test_agreements_are_symmetric_with_nothing_on_the_diagonal() -> None:
    labels = [SampleLabel.parse(text) for text in ("HI-HAT: CLOSED", "HI-HAT: OPEN", "SNARE")]

    agreements = agreement_matrix(labels)

    assert agreements[0, 1] == agreements[1, 0] == 1 / 3
    assert agreements[0, 2] == 0.0
    assert np.all(np.diag(agreements) == 0.0)


def test_a_row_ranks_the_others_nearest_first_and_leaves_its_own_group_out() -> None:
    vectors = np.array([[0.0], [0.1], [1.0], [1.1]])
    groups = np.array([0, 0, 1, 2])

    ranking = nearest_first(vectors, groups=groups)

    assert ranking[0].tolist() == [2, 3, -1]
    assert ranking[2].tolist() == [3, 1, 0]


def test_a_perfect_neighborhood_scores_one_and_an_empty_one_reads_as_nothing_to_find() -> None:
    agreements = np.array([[0.0, 1.0, 0.5], [1.0, 0.0, 0.0], [0.5, 0.0, 0.0]])
    ranking = np.array([[1, 2], [0, 2], [0, 1]])

    scores = ndcg_per_query(agreements, ranking, neighborhood=2)

    assert scores[0] == 1.0
    assert scores[1] == 1.0
    assert not np.isnan(scores[2])
    assert np.isnan(ndcg_per_query(np.zeros((2, 2)), np.array([[1], [0]]), neighborhood=1)).all()


def test_a_reversed_neighborhood_scores_below_one() -> None:
    agreements = np.array([[0.0, 1.0, 0.5], [1.0, 0.0, 0.0], [0.5, 0.0, 0.0]])

    right = ndcg_per_query(agreements, np.array([[1, 2], [0, 2], [0, 1]]), neighborhood=2)[0]
    reversed_order = ndcg_per_query(agreements, np.array([[2, 1], [0, 2], [0, 1]]), neighborhood=2)[0]

    assert reversed_order < right == 1.0
