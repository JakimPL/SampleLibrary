from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import Connection

from samplecloud.evaluation.corpus import load_corpus
from samplecloud.evaluation.notes import note_agreement
from samplecloud.evaluation.settings import EvaluationScope, EvaluationSettings
from tests.samplecloud.evaluation.conftest import SeededCatalog, seed_catalog

SETTINGS = EvaluationSettings(random_seed=0, fold_count=4, neighbor_count=3)


def test_a_descriptor_that_separates_the_categories_agrees_with_the_note_events(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """Each seeded category is played at its own number of pitches, so the two targets line up."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    agreement = note_agreement(corpus, settings=SETTINGS)
    assert agreement is not None

    by_target = {score.target: score.spearman for score in agreement.targets}
    assert by_target["log2_pitch_count"] > 0.8
    assert agreement.coverage == pytest.approx(1.0)


def test_the_note_score_reports_how_many_samples_were_struck_often_enough(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """Pitch count is bounded above by strike count, so the well-struck subset is reported apart."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    agreement = note_agreement(corpus, settings=SETTINGS)
    assert agreement is not None

    assert agreement.well_struck_sample_count == corpus.sample_count
    assert {score.target for score in agreement.well_struck_targets} == {"log2_pitch_count", "log2_span"}


def test_two_passes_over_one_corpus_report_the_same_numbers(
    connection: Connection, separable_catalog: SeededCatalog
) -> None:
    """The gate this harness exists to hold: a seed fixes every split and every draw."""
    corpus = load_corpus(connection, experiment_id=separable_catalog.experiment_id, scope=EvaluationScope.CATALOG)

    assert note_agreement(corpus, settings=SETTINGS) == note_agreement(corpus, settings=SETTINGS)


def test_settings_reject_a_pass_that_could_not_be_folded() -> None:
    with pytest.raises(ValueError, match="at least two folds"):
        EvaluationSettings(fold_count=1)


def test_settings_reject_an_empty_offset_grid() -> None:
    with pytest.raises(ValueError, match="at least one semitone offset"):
        EvaluationSettings(semitone_offsets=())


def test_a_corpus_the_note_events_barely_reach_cannot_be_folded(connection: Connection) -> None:
    catalog = seed_catalog(connection, separable=True)
    corpus = load_corpus(connection, experiment_id=catalog.experiment_id, scope=EvaluationScope.CATALOG)
    unreached = replace(corpus, note_statistics=tuple(None for _ in corpus.note_statistics))

    assert note_agreement(unreached, settings=SETTINGS) is None


def test_settings_reject_a_pass_with_no_neighbors() -> None:
    with pytest.raises(ValueError, match="at least one neighbor"):
        EvaluationSettings(neighbor_count=0)


def test_settings_reject_a_pass_with_no_probes() -> None:
    with pytest.raises(ValueError, match="at least one probe"):
        EvaluationSettings(probe_count=0)
