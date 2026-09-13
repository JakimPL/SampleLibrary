from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import Connection

from samplecloud.evaluation.categories import category_agreement
from samplecloud.evaluation.corpus import load_corpus
from samplecloud.evaluation.notes import note_agreement
from samplecloud.evaluation.settings import EvaluationSettings
from samplecore.models.category import SampleCategory
from tests.samplecloud.evaluation.conftest import SEEDED_CATEGORIES, SeededCatalog, seed_catalog

SETTINGS = EvaluationSettings(random_seed=0, fold_count=4, neighbor_count=3)


def test_a_descriptor_that_separates_the_categories_scores_well(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    agreement = category_agreement(corpus, settings=SETTINGS)

    assert agreement.accuracy > 0.9
    assert agreement.macro_f1 > 0.9
    assert {score.category for score in agreement.per_category} == set(SEEDED_CATEGORIES)


def test_a_descriptor_carrying_no_structure_scores_near_chance(connection: Connection) -> None:
    """A metric earns trust by reporting an absence rather than finding structure in noise."""
    catalog = seed_catalog(connection, separable=False)
    corpus = load_corpus(connection, experiment_id=catalog.experiment_id)

    agreement = category_agreement(corpus, settings=SETTINGS)

    assert agreement.accuracy < 0.6


def test_the_category_score_reports_the_share_of_the_catalog_it_describes(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """A keyword reaches a tenth of the real catalog, so any reader has to be told what was scored."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    agreement = category_agreement(corpus, settings=SETTINGS)

    assert agreement.coverage == pytest.approx(1.0)
    assert agreement.scored_sample_count == corpus.sample_count


def test_uncategorized_samples_stay_out_of_the_category_score(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """It records that no keyword matched, so scoring it would reward gathering the unnamed."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    agreement = category_agreement(corpus, settings=SETTINGS)

    assert str(SampleCategory.UNCATEGORIZED) not in {score.category for score in agreement.per_category}


def test_a_descriptor_that_separates_the_categories_agrees_with_the_note_events(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """Each seeded category is played at its own number of pitches, so the two targets line up."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    agreement = note_agreement(corpus, settings=SETTINGS)

    by_target = {score.target: score.spearman for score in agreement.targets}
    assert by_target["log2_pitch_count"] > 0.8
    assert agreement.coverage == pytest.approx(1.0)


def test_the_note_score_reports_how_many_samples_were_struck_often_enough(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """Pitch count is bounded above by strike count, so the well-struck subset is reported apart."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    agreement = note_agreement(corpus, settings=SETTINGS)

    assert agreement.well_struck_sample_count == corpus.sample_count
    assert {score.target for score in agreement.well_struck_targets} == {"log2_pitch_count", "log2_span"}


def test_two_passes_over_one_corpus_report_the_same_numbers(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """The gate this harness exists to hold: a seed fixes every split and every draw."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id)

    assert category_agreement(corpus, settings=SETTINGS) == category_agreement(corpus, settings=SETTINGS)
    assert note_agreement(corpus, settings=SETTINGS) == note_agreement(corpus, settings=SETTINGS)


def test_settings_reject_a_pass_that_could_not_be_folded() -> None:
    with pytest.raises(ValueError, match="at least two folds"):
        EvaluationSettings(fold_count=1)


def test_settings_reject_an_empty_offset_grid() -> None:
    with pytest.raises(ValueError, match="at least one semitone offset"):
        EvaluationSettings(semitone_offsets=())


def test_a_corpus_carrying_one_category_cannot_be_scored(connection: Connection) -> None:
    catalog = seed_catalog(connection, separable=True)
    corpus = load_corpus(connection, experiment_id=catalog.experiment_id)
    single = replace(corpus, categories=tuple(SampleCategory.KICK for _ in corpus.categories))

    with pytest.raises(ValueError, match="fewer than two categories"):
        category_agreement(single, settings=SETTINGS)


def test_a_corpus_the_note_events_barely_reach_cannot_be_folded(connection: Connection) -> None:
    catalog = seed_catalog(connection, separable=True)
    corpus = load_corpus(connection, experiment_id=catalog.experiment_id)
    unreached = replace(corpus, note_statistics=tuple(None for _ in corpus.note_statistics))

    with pytest.raises(ValueError, match="too few to score"):
        note_agreement(unreached, settings=SETTINGS)


def test_settings_reject_a_pass_with_no_neighbors() -> None:
    with pytest.raises(ValueError, match="at least one neighbor"):
        EvaluationSettings(neighbor_count=0)


def test_settings_reject_a_pass_with_no_probes() -> None:
    with pytest.raises(ValueError, match="at least one probe"):
        EvaluationSettings(probe_count=0)
