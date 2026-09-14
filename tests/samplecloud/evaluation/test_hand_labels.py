from __future__ import annotations

import pytest
from sqlalchemy import Connection

from samplecloud.evaluation.corpus import load_corpus
from samplecloud.evaluation.hand_labels import MINIMUM_TAG_SUPPORT, hand_label_agreement
from samplecloud.evaluation.settings import EvaluationScope, EvaluationSettings
from tests.samplecloud.evaluation.conftest import SeededCatalog, label_catalog, seed_catalog

SETTINGS = EvaluationSettings(random_seed=0, fold_count=4, neighbor_count=3)


def test_a_descriptor_that_gathers_what_a_person_labeled_alike_scores_well(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    label_catalog(connection, separable_catalog)
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    agreement = hand_label_agreement(corpus, settings=SETTINGS)

    assert agreement.ndcg > 0.9
    assert agreement.precision_at_one > 0.9
    assert agreement.ndcg > agreement.ndcg_chance
    assert agreement.ndcg_interval[0] <= agreement.ndcg <= agreement.ndcg_interval[1]


def test_a_descriptor_carrying_no_structure_scores_near_chance(connection: Connection) -> None:
    catalog = seed_catalog(connection, separable=False)
    label_catalog(connection, catalog)
    corpus = load_corpus(connection, experiment_id=catalog.experiment_id, scope=EvaluationScope.CATALOG)

    agreement = hand_label_agreement(corpus, settings=SETTINGS)

    assert abs(agreement.ndcg - agreement.ndcg_chance) < 0.2
    assert abs(agreement.precision_at_one - agreement.precision_at_one_chance) < 0.35


def test_each_tag_with_enough_support_is_scored_on_its_own(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """A specification carried by too few samples stays out, and SYNTH under BASS is a tag of its own."""
    label_catalog(connection, separable_catalog)
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    agreement = hand_label_agreement(corpus, settings=SETTINGS)

    scored = {score.path: score for score in agreement.per_tag}
    assert {"KICK", "SNARE", "BASS", "BASS: SYNTH", "LEAD", "SYNTH"} <= set(scored)
    assert "KICK: SOFT" not in scored
    assert scored["SYNTH"].support == 8
    assert all(score.support >= MINIMUM_TAG_SUPPORT for score in agreement.per_tag)
    assert scored["SNARE"].average_precision > 0.9


def test_reading_labels_to_one_level_folds_a_specification_into_its_category(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    label_catalog(connection, separable_catalog)
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    agreement = hand_label_agreement(corpus, settings=EvaluationSettings(random_seed=0, label_depth=1))

    assert agreement.label_depth == 1
    assert "BASS: SYNTH" not in {score.path for score in agreement.per_tag}


def test_the_score_reports_the_share_of_the_catalog_a_person_labeled(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    labeled = label_catalog(connection, separable_catalog, every=2)
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    agreement = hand_label_agreement(corpus, settings=SETTINGS)

    assert agreement.labeled_sample_count == len(labeled)
    assert agreement.coverage == pytest.approx(len(labeled) / corpus.sample_count)


def test_too_few_labels_to_read_a_score_from_say_so(connection: Connection, separable_catalog: SeededCatalog) -> None:
    label_catalog(connection, separable_catalog, every=8)
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    with pytest.raises(ValueError, match="labeled samples carry a vector"):
        hand_label_agreement(corpus, settings=SETTINGS)


def test_a_label_depth_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one level"):
        EvaluationSettings(label_depth=0)
