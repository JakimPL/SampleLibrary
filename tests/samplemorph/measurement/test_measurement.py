from __future__ import annotations

import numpy as np
import pytest

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplemorph.canonicalizers.log_frequency import build_log_frequency_canonicalizer
from samplemorph.measurement.comparison import grid_distance, log_mel_distance_db, log_mel_spectrum
from samplemorph.measurement.corpus import ProbeSample, unrelated_pairs
from samplemorph.measurement.equivariance import (
    EquivarianceTrial,
    equivariance_trials,
    summarize_equivariance,
    unrelated_grid_distance,
)
from samplemorph.measurement.reconstruction import (
    ReconstructionRung,
    reconstruction_trials,
    summarize_reconstruction,
    unrelated_distance_db,
)
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone, noise_burst

PROBE_OFFSETS = (-7.0, 7.0)
RANDOM_SEED = 3


def _probe(index: int, mono: np.ndarray) -> ProbeSample:
    sample = Sample(
        hash=format(index, "064x"),
        depth=16,
        channels=ChannelLayout.MONO,
        frames=mono.shape[0],
    )
    return ProbeSample(sample=sample, mono=mono)


@pytest.fixture(name="probes")
def probes_fixture() -> tuple[ProbeSample, ...]:
    return (
        _probe(1, harmonic_tone(TEST_FRAME_COUNT, frequency=220.0)[:, 0]),
        _probe(2, harmonic_tone(TEST_FRAME_COUNT, frequency=440.0)[:, 0]),
        _probe(3, noise_burst(TEST_FRAME_COUNT, seed=5)[:, 0]),
    )


def test_grid_distance_reports_zero_for_one_grid_against_itself() -> None:
    grid = np.linspace(0.0, 1.0, 24).reshape(6, 4)

    assert grid_distance(grid, grid) == pytest.approx(0.0)


def test_log_mel_distance_reports_zero_for_one_waveform_against_itself() -> None:
    spectrum = log_mel_spectrum(harmonic_tone(TEST_FRAME_COUNT, frequency=330.0)[:, 0])

    assert log_mel_distance_db(spectrum, spectrum) == pytest.approx(0.0)


def test_log_mel_distance_separates_a_tone_from_a_noise_burst() -> None:
    tone = log_mel_spectrum(harmonic_tone(TEST_FRAME_COUNT, frequency=330.0)[:, 0])
    burst = log_mel_spectrum(noise_burst(TEST_FRAME_COUNT, seed=0)[:, 0])

    assert log_mel_distance_db(tone, burst) > 0.0


def test_unrelated_pairs_names_two_distinct_samples_each_time() -> None:
    pairs = unrelated_pairs(10, pair_count=25, random_seed=RANDOM_SEED)

    assert len(pairs) == 25
    assert all(first != second for first, second in pairs)
    assert all(0 <= index < 10 for pair in pairs for index in pair)


def test_unrelated_pairs_repeats_its_draw_for_one_seed() -> None:
    first = unrelated_pairs(10, pair_count=5, random_seed=RANDOM_SEED)
    second = unrelated_pairs(10, pair_count=5, random_seed=RANDOM_SEED)

    assert first == second


def test_equivariance_trials_cover_every_probe_at_every_offset(probes: tuple[ProbeSample, ...]) -> None:
    canonicalizer = build_log_frequency_canonicalizer()

    trials = equivariance_trials(probes, canonicalizer, semitone_offsets=PROBE_OFFSETS)

    assert len(trials) == len(probes) * len(PROBE_OFFSETS)
    assert {trial.semitone_offset for trial in trials} == set(PROBE_OFFSETS)
    assert all(trial.grid_distance >= 0.0 for trial in trials)


def test_summarizing_equivariance_reports_one_entry_per_offset(probes: tuple[ProbeSample, ...]) -> None:
    canonicalizer = build_log_frequency_canonicalizer()
    trials = equivariance_trials(probes, canonicalizer, semitone_offsets=PROBE_OFFSETS)
    unrelated = unrelated_grid_distance(probes, canonicalizer, pair_count=4, random_seed=RANDOM_SEED)

    summary = summarize_equivariance(trials, canonicalizer_name="log_frequency", unrelated_distance=unrelated)

    assert tuple(offset.semitone_offset for offset in summary.offsets) == tuple(sorted(PROBE_OFFSETS))
    assert all(offset.trial_count == len(probes) for offset in summary.offsets)
    assert summary.explained_share <= 1.0


def test_summarizing_equivariance_rejects_an_empty_probe() -> None:
    with pytest.raises(ValueError, match="nothing to summarize"):
        summarize_equivariance((), canonicalizer_name="log_frequency", unrelated_distance=1.0)


def test_the_explained_share_reads_as_the_fraction_of_the_unrelated_distance_removed() -> None:
    trials = (
        EquivarianceTrial(
            sample_hash="a" * 64, semitone_offset=7.0, grid_distance=0.25, translation_error_semitones=0.0
        ),
    )

    summary = summarize_equivariance(trials, canonicalizer_name="stub", unrelated_distance=1.0)

    assert summary.explained_share == pytest.approx(0.75)


def test_reconstruction_trials_record_both_rungs_for_every_probe(probes: tuple[ProbeSample, ...]) -> None:
    canonicalizer = build_log_frequency_canonicalizer()

    trials = reconstruction_trials(probes, canonicalizer)

    assert len(trials) == len(probes) * len(ReconstructionRung)
    assert {trial.rung for trial in trials} == set(ReconstructionRung)


def test_summarizing_reconstruction_reports_the_cost_of_estimating_phase(
    probes: tuple[ProbeSample, ...],
) -> None:
    """Splitting the round trip at the phase estimate is what makes its cost attributable."""
    canonicalizer = build_log_frequency_canonicalizer()
    trials = reconstruction_trials(probes, canonicalizer)
    unrelated = unrelated_distance_db(probes, pair_count=4, random_seed=RANDOM_SEED)

    summary = summarize_reconstruction(trials, canonicalizer_name="log_frequency", unrelated_distance=unrelated)

    oracle = summary.rung(ReconstructionRung.ORACLE_PHASE)
    estimated = summary.rung(ReconstructionRung.ESTIMATED_PHASE)
    assert summary.phase_estimate_cost_db == pytest.approx(estimated.median_distance_db - oracle.median_distance_db)
    assert oracle.trial_count == estimated.trial_count == len(probes)


def test_summarizing_reconstruction_rejects_an_empty_probe() -> None:
    with pytest.raises(ValueError, match="nothing to summarize"):
        summarize_reconstruction((), canonicalizer_name="log_frequency", unrelated_distance=1.0)


def test_asking_a_summary_for_a_rung_it_holds_no_trials_on_says_so(probes: tuple[ProbeSample, ...]) -> None:
    oracle_only = tuple(
        trial
        for trial in reconstruction_trials(probes, build_log_frequency_canonicalizer())
        if trial.rung is ReconstructionRung.ORACLE_PHASE
    )
    summary = summarize_reconstruction(oracle_only, canonicalizer_name="log_frequency", unrelated_distance=1.0)

    with pytest.raises(KeyError, match="estimated_phase"):
        summary.rung(ReconstructionRung.ESTIMATED_PHASE)
