from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly
from trackmod.binary.pcm.quantise import dequantise, quantise
from trackmod.core.samples.depth import BitDepth

from sampleextract.equivalence.scoring import (
    BIT_DEPTH_MINIMUM_CONFIDENCE,
    RESAMPLED_MINIMUM_CONFIDENCE,
    score_bit_depth_variant,
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


def test_score_bit_depth_variant_scores_a_true_quantisation_pair_highly() -> None:
    waveform = _tonal_waveform(2000)
    eight_bit_roundtrip = dequantise(quantise(waveform, BitDepth.EIGHT), BitDepth.EIGHT)

    score = score_bit_depth_variant(waveform, eight_bit_roundtrip)

    assert score.confidence > BIT_DEPTH_MINIMUM_CONFIDENCE


def test_score_bit_depth_variant_scores_two_independent_waveforms_at_zero() -> None:
    first = _tonal_waveform(2000)
    second = np.random.default_rng(1).uniform(-1.0, 1.0, (2000, 1))

    score = score_bit_depth_variant(first, second)

    assert score.confidence == 0.0


def test_score_resampled_variant_scores_a_true_resample_pair_highly() -> None:
    original = _tonal_waveform(4410)
    resampled = resample_poly(original, up=22050, down=44100, axis=0)

    score = score_resampled_variant(original, resampled)

    assert score is not None
    assert score.confidence > RESAMPLED_MINIMUM_CONFIDENCE
    assert score.evidence["resample_ratio"] == 2.0


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
