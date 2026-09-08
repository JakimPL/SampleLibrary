from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray
from scipy.signal import resample_poly
from trackmod.binary.pcm.quantise import dequantise, quantise
from trackmod.core.samples.depth import BitDepth

from sampleextract.equivalence.scoring import (
    GAIN_VARIANT_MINIMUM_CONFIDENCE,
    MAX_TRIM_MISMATCH_FRAMES,
    MAXIMUM_GAIN,
    RESAMPLED_MINIMUM_CONFIDENCE,
    score_gain_variant,
    score_resampled_variant,
)

SAMPLE_RATE = 44100


def _tonal_waveform(frames: int, *, sample_rate: int = SAMPLE_RATE) -> NDArray[np.float64]:
    """A smooth, band-limited synthetic waveform -- a sum of a few sinusoids, not white noise,
    since resampling only preserves the band-limited content real tracker samples actually carry.
    """
    time = np.arange(frames) / sample_rate
    waveform = (
        0.5 * np.sin(2 * np.pi * 220 * time)
        + 0.3 * np.sin(2 * np.pi * 440 * time)
        + 0.2 * np.sin(2 * np.pi * 880 * time)
    )
    return waveform.reshape(-1, 1)


def test_score_gain_variant_scores_a_true_quantization_pair_highly() -> None:
    waveform = _tonal_waveform(2000)
    eight_bit_roundtrip = dequantise(quantise(waveform, BitDepth.EIGHT), BitDepth.EIGHT)

    score = score_gain_variant(waveform, eight_bit_roundtrip, depth_a=BitDepth.SIXTEEN, depth_b=BitDepth.EIGHT)

    assert score is not None
    assert score.confidence > GAIN_VARIANT_MINIMUM_CONFIDENCE
    assert score.evidence["gain"] == pytest.approx(1.0, abs=0.01)


def test_score_gain_variant_scores_a_true_amplification_pair_highly() -> None:
    waveform = _tonal_waveform(2000)
    louder = waveform * 2.0

    score = score_gain_variant(waveform, louder, depth_a=BitDepth.SIXTEEN, depth_b=BitDepth.SIXTEEN)

    assert score is not None
    assert score.confidence > GAIN_VARIANT_MINIMUM_CONFIDENCE
    assert score.evidence["gain"] == pytest.approx(2.0)


def test_score_gain_variant_scores_a_compound_depth_and_gain_pair_highly() -> None:
    waveform = _tonal_waveform(2000)
    quieter_and_requantized = dequantise(quantise(waveform * 0.5, BitDepth.EIGHT), BitDepth.EIGHT)

    score = score_gain_variant(waveform, quieter_and_requantized, depth_a=BitDepth.SIXTEEN, depth_b=BitDepth.EIGHT)

    assert score is not None
    assert score.confidence > GAIN_VARIANT_MINIMUM_CONFIDENCE
    assert score.evidence["gain"] == pytest.approx(0.5, abs=0.01)


def test_score_gain_variant_does_not_match_two_independent_waveforms() -> None:
    """An uncorrelated pair's least-squares gain is noise around zero, as likely to land outside
    the plausible range (a None verdict) as inside it at confidence 0.0 -- either is a non-match.
    """
    first = _tonal_waveform(2000)
    second = np.random.default_rng(1).uniform(-1.0, 1.0, (2000, 1))

    score = score_gain_variant(first, second, depth_a=BitDepth.SIXTEEN, depth_b=BitDepth.SIXTEEN)

    assert score is None or score.confidence == 0.0


def test_score_gain_variant_returns_none_for_a_silent_reference() -> None:
    silence = np.zeros((2000, 1))
    tone = _tonal_waveform(2000)

    assert score_gain_variant(silence, tone, depth_a=BitDepth.SIXTEEN, depth_b=BitDepth.SIXTEEN) is None


def test_score_gain_variant_returns_none_for_an_implausible_gain() -> None:
    waveform = _tonal_waveform(2000)
    extreme = waveform * (MAXIMUM_GAIN * 2.0)

    score = score_gain_variant(waveform, extreme, depth_a=BitDepth.SIXTEEN, depth_b=BitDepth.SIXTEEN)

    assert score is None


def test_score_gain_variant_matches_a_pair_whose_trimmed_lengths_differ_slightly() -> None:
    waveform = _tonal_waveform(2000)
    with_extra_trailing_frames = np.pad(waveform, ((0, MAX_TRIM_MISMATCH_FRAMES), (0, 0)))

    score = score_gain_variant(waveform, with_extra_trailing_frames, depth_a=BitDepth.SIXTEEN, depth_b=BitDepth.SIXTEEN)

    assert score is not None
    assert score.confidence > GAIN_VARIANT_MINIMUM_CONFIDENCE
    assert score.evidence["gain"] == pytest.approx(1.0)


def test_score_gain_variant_returns_none_when_lengths_differ_beyond_the_mismatch_tolerance() -> None:
    waveform = _tonal_waveform(2000)
    with_far_more_trailing_frames = np.pad(waveform, ((0, MAX_TRIM_MISMATCH_FRAMES + 1), (0, 0)))

    score = score_gain_variant(
        waveform, with_far_more_trailing_frames, depth_a=BitDepth.SIXTEEN, depth_b=BitDepth.SIXTEEN
    )

    assert score is None


def test_score_resampled_variant_scores_a_true_resample_pair_highly() -> None:
    original = _tonal_waveform(4410)
    resampled = resample_poly(original, up=22050, down=44100, axis=0)

    score = score_resampled_variant(original, resampled)

    assert score is not None
    assert score.confidence > RESAMPLED_MINIMUM_CONFIDENCE
    assert score.evidence["resample_ratio"] == 2.0
    assert score.evidence["gain"] == pytest.approx(1.0, abs=0.05)


def test_score_resampled_variant_recovers_the_gain_of_a_compound_resample_and_amplitude_pair() -> None:
    original = _tonal_waveform(4410)
    louder_original = original * 1.5
    resampled = resample_poly(original, up=22050, down=44100, axis=0)

    score = score_resampled_variant(louder_original, resampled)

    assert score is not None
    assert score.confidence > RESAMPLED_MINIMUM_CONFIDENCE
    assert score.evidence["gain"] == pytest.approx(1.5, abs=0.05)


def test_score_resampled_variant_clamps_confidence_to_one_despite_floating_point_overshoot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A near-perfect match's raw Pearson correlation can round to fractionally above 1.0 -- this
    must never reach a RelationScore, since SampleRelation.confidence rejects anything past 1.0.
    """
    monkeypatch.setattr(
        "sampleextract.equivalence.scoring._pearson_correlation", lambda first, second: 1.0000000000000002
    )
    original = _tonal_waveform(4410)
    resampled = resample_poly(original, up=22050, down=44100, axis=0)

    score = score_resampled_variant(original, resampled)

    assert score is not None
    assert score.confidence == 1.0


def test_score_resampled_variant_tolerates_a_trimmed_lead_in() -> None:
    original = _tonal_waveform(44100)
    resampled = resample_poly(original, up=22050, down=44100, axis=0)
    trimmed = resampled[5:]

    score = score_resampled_variant(original, trimmed)

    assert score is not None
    assert score.confidence > RESAMPLED_MINIMUM_CONFIDENCE
    assert score.evidence["lag_frames"] != 0.0


def test_score_resampled_variant_scores_two_unrelated_waveforms_low() -> None:
    first = _tonal_waveform(4410)
    second = np.random.default_rng(2).uniform(-1.0, 1.0, (2200, 1))

    score = score_resampled_variant(first, second)

    assert score is not None
    assert score.confidence < RESAMPLED_MINIMUM_CONFIDENCE


def test_score_resampled_variant_returns_none_for_a_silent_waveform() -> None:
    silence = np.zeros((2000, 1))
    tone = _tonal_waveform(1000)

    assert score_resampled_variant(silence, tone) is None


def test_score_resampled_variant_handles_the_resampled_length_landing_over_target() -> None:
    """152363/34506 frames is a real combination whose bounded-denominator ratio approximation
    resamples two frames past the target length -- this must be trimmed, not left misaligned.
    """
    long_waveform = _tonal_waveform(152363)
    short_waveform = _tonal_waveform(34506)

    score = score_resampled_variant(long_waveform, short_waveform)

    assert score is not None
    assert score.evidence["resample_ratio"] == 152363 / 34506


def test_score_resampled_variant_handles_the_resampled_length_landing_under_target() -> None:
    """40023/20011 frames is the equivalent under-target combination, exercising the zero-pad path."""
    long_waveform = _tonal_waveform(40023)
    short_waveform = _tonal_waveform(20011)

    score = score_resampled_variant(long_waveform, short_waveform)

    assert score is not None
    assert score.evidence["resample_ratio"] == 40023 / 20011


def test_score_resampled_variant_handles_frame_counts_shorter_than_the_lag_search_window() -> None:
    """Calling the scorer directly, bypassing candidate generation's own minimum-frames floor,
    with waveforms shorter than the lag search window must not let the search wrap around the
    array's end at its most extreme offsets.
    """
    long_waveform = _tonal_waveform(40)
    short_waveform = _tonal_waveform(20)

    score = score_resampled_variant(long_waveform, short_waveform)

    assert score is not None


def test_score_resampled_variant_caps_the_comparison_length_for_long_waveforms() -> None:
    """A genuine resampled pair far longer than MAX_COMPARISON_FRAMES still scores highly -- the
    lag search only needs to examine a bounded prefix of the content to confirm a match.
    """
    original = _tonal_waveform(88200)
    resampled = resample_poly(original, up=22050, down=44100, axis=0)

    score = score_resampled_variant(original, resampled)

    assert score is not None
    assert score.confidence > RESAMPLED_MINIMUM_CONFIDENCE
