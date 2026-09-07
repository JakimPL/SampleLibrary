from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.models.channels import ChannelLayout
from samplecore.models.relation import RelationType, SampleRelation
from samplecore.models.sample import Sample
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from sampleextract.equivalence.calibration import (
    CalibrationTrial,
    gain_variant_calibration_trials,
    most_marginal_relations,
    resampled_variant_calibration_trials,
    separation_gap,
    trailing_trim_calibration_trials,
)
from sampleextract.equivalence.scoring import (
    GAIN_VARIANT_MINIMUM_CONFIDENCE,
    MAX_TRIM_MISMATCH_FRAMES,
    RESAMPLED_MINIMUM_CONFIDENCE,
)


def test_separation_gap_is_positive_when_every_match_outscores_every_non_match() -> None:
    trials = (
        CalibrationTrial(label="match", is_genuine_match=True, confidence=0.9, gain=1.0),
        CalibrationTrial(label="non_match", is_genuine_match=False, confidence=0.1, gain=None),
    )

    assert separation_gap(trials) == pytest.approx(0.8)


def test_separation_gap_is_not_positive_when_a_non_match_outscores_a_match() -> None:
    trials = (
        CalibrationTrial(label="match", is_genuine_match=True, confidence=0.4, gain=1.0),
        CalibrationTrial(label="non_match", is_genuine_match=False, confidence=0.5, gain=None),
    )

    assert separation_gap(trials) <= 0.0


def test_separation_gap_requires_at_least_one_match_and_one_non_match() -> None:
    only_matches = (CalibrationTrial(label="match", is_genuine_match=True, confidence=0.9, gain=1.0),)

    with pytest.raises(ValueError, match="at least one genuine match and one non-match"):
        separation_gap(only_matches)


def test_gain_variant_calibration_trials_separate_every_genuine_case_from_unrelated_content() -> None:
    trials = gain_variant_calibration_trials(gains=(2.0, 0.5), rng_seed=1)

    assert separation_gap(trials) > 0.0
    genuine_labels = {trial.label for trial in trials if trial.is_genuine_match}
    assert genuine_labels == {"bit_depth", "amplification", "compound_depth_gain"}
    for trial in trials:
        if trial.is_genuine_match:
            assert trial.confidence > GAIN_VARIANT_MINIMUM_CONFIDENCE
        else:
            assert trial.confidence < GAIN_VARIANT_MINIMUM_CONFIDENCE


def test_trailing_trim_calibration_trials_separate_tolerated_trims_from_unrelated_content() -> None:
    trials = trailing_trim_calibration_trials(trailing_frame_counts=(0, 5, 16, MAX_TRIM_MISMATCH_FRAMES), rng_seed=2)

    assert separation_gap(trials) > 0.0
    for trial in trials:
        if trial.is_genuine_match:
            assert trial.confidence > GAIN_VARIANT_MINIMUM_CONFIDENCE
            assert trial.gain == pytest.approx(1.0)
        else:
            assert trial.confidence < GAIN_VARIANT_MINIMUM_CONFIDENCE


def test_resampled_variant_calibration_trials_separate_compound_matches_from_unrelated_content() -> None:
    """Each genuine trial's recovered gain is 1.5 or its reciprocal depending on which side of the
    pair `score_resampled_variant` treats as the resampled one -- a property of that scorer's own
    evidence, not something this calibration helper controls, so only its presence is checked here.
    """
    trials = resampled_variant_calibration_trials(ratios=(2.0, 0.5), rng_seed=3)

    assert separation_gap(trials) > 0.0
    for trial in trials:
        if trial.is_genuine_match:
            assert trial.confidence > RESAMPLED_MINIMUM_CONFIDENCE
            assert trial.gain is not None
        else:
            assert trial.confidence < RESAMPLED_MINIMUM_CONFIDENCE


def _insert_relation(
    connection: Connection,
    repository: PostgresSampleRelationRepository,
    *,
    seed: int,
    relation_type: RelationType,
    confidence: float,
) -> SampleRelation:
    sample_repository = PostgresSampleRepository(connection)
    subject_hash, reference_hash = format(seed, "064x"), format(seed + 1, "064x")
    for sample_hash in (subject_hash, reference_hash):
        sample_repository.upsert(
            Sample(hash=sample_hash, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=4)
        )

    relation = SampleRelation(
        id=repository.next_id(),
        subject_hash=subject_hash,
        reference_hash=reference_hash,
        relation_type=relation_type,
        method="test/v1",
        confidence=confidence,
        evidence={},
        detected_at=datetime.now(UTC),
    )
    repository.upsert(relation)
    return relation


def test_most_marginal_relations_returns_the_least_confident_of_the_requested_type_first(
    connection: Connection,
) -> None:
    repository = PostgresSampleRelationRepository(connection)
    weakest = _insert_relation(
        connection, repository, seed=1, relation_type=RelationType.AMPLIFICATION_VARIANT, confidence=0.6
    )
    strongest = _insert_relation(
        connection, repository, seed=3, relation_type=RelationType.AMPLIFICATION_VARIANT, confidence=0.95
    )
    _insert_relation(connection, repository, seed=5, relation_type=RelationType.BIT_DEPTH_VARIANT, confidence=0.5)

    result = most_marginal_relations(connection, relation_type=RelationType.AMPLIFICATION_VARIANT, limit=1)

    assert result == (weakest,)
    assert strongest not in result
