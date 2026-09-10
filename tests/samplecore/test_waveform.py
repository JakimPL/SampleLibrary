from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from samplecore.waveform import (
    average_to_fraction_points,
    compute_waveform_peaks,
    fold_to_mono,
    remove_dc_offset,
    remove_subsonic,
    resample_to_fraction_points,
    subsonic_sections,
    triangular_weights,
    trim_trailing_silence,
)

CONTAINER_RATE_HZ = 44100
LOW_HEARD_RATE_HZ = 8363
TONE_SECONDS = 2.0
TONE_AMPLITUDE = 0.1
CLICK_SECONDS = 0.001
DC_OFFSET = 0.25


@dataclass(frozen=True)
class SubsonicToneCase:
    frequency_hz: float
    sample_rate_hz: int
    lowest_gain_db: float
    highest_gain_db: float


SUBSONIC_TONE_CASES = (
    SubsonicToneCase(frequency_hz=10.0, sample_rate_hz=CONTAINER_RATE_HZ, lowest_gain_db=-200.0, highest_gain_db=-50.0),
    SubsonicToneCase(frequency_hz=100.0, sample_rate_hz=CONTAINER_RATE_HZ, lowest_gain_db=-0.5, highest_gain_db=0.5),
    SubsonicToneCase(frequency_hz=100.0, sample_rate_hz=LOW_HEARD_RATE_HZ, lowest_gain_db=-0.5, highest_gain_db=0.5),
)


def _tone(frequency_hz: float, *, sample_rate_hz: int) -> np.ndarray:
    times = np.arange(int(TONE_SECONDS * sample_rate_hz)) / sample_rate_hz
    return TONE_AMPLITUDE * np.sin(2.0 * np.pi * frequency_hz * times)


def _middle_rms(signal: np.ndarray) -> float:
    quarter = signal.shape[0] // 4
    return float(np.sqrt(np.mean(signal[quarter:-quarter] ** 2)))


def _energy_centroid(signal: np.ndarray) -> float:
    energy = signal**2
    return float((np.arange(signal.shape[0]) * energy).sum() / energy.sum())


@pytest.mark.parametrize("case", SUBSONIC_TONE_CASES)
def test_remove_subsonic_rejects_rumble_and_passes_the_audible_band(case: SubsonicToneCase) -> None:
    tone = _tone(case.frequency_hz, sample_rate_hz=case.sample_rate_hz)

    filtered = remove_subsonic(tone, sample_rate_hz=case.sample_rate_hz)

    gain_db = 20.0 * np.log10(_middle_rms(filtered) / _middle_rms(tone))
    assert case.lowest_gain_db <= gain_db <= case.highest_gain_db


def test_remove_subsonic_removes_a_constant_offset() -> None:
    offset = np.full(int(TONE_SECONDS * CONTAINER_RATE_HZ), DC_OFFSET)

    filtered = remove_subsonic(offset, sample_rate_hz=CONTAINER_RATE_HZ)

    assert _middle_rms(filtered) < DC_OFFSET * 1e-3


def test_remove_subsonic_keeps_a_click_where_it_was() -> None:
    click_length = int(CLICK_SECONDS * CONTAINER_RATE_HZ)
    signal = np.zeros(int(TONE_SECONDS * CONTAINER_RATE_HZ))
    start = signal.shape[0] // 2
    signal[start : start + click_length] = np.hanning(click_length)

    filtered = remove_subsonic(signal, sample_rate_hz=CONTAINER_RATE_HZ)

    assert abs(_energy_centroid(filtered) - _energy_centroid(signal)) < 2.0


def test_remove_subsonic_reads_a_signal_shorter_than_its_settling_span() -> None:
    short = np.array([0.1, -0.2, 0.3, -0.1, 0.05])

    filtered = remove_subsonic(short, sample_rate_hz=CONTAINER_RATE_HZ)

    assert filtered.shape == short.shape
    assert np.isfinite(filtered).all()


def test_subsonic_sections_stay_finite_at_a_low_heard_rate() -> None:
    sections = subsonic_sections(LOW_HEARD_RATE_HZ)

    assert np.isfinite(sections).all()
    assert sections.shape[1] == 6


def test_compute_waveform_peaks_returns_the_requested_bucket_count() -> None:
    pcm = np.linspace(-1.0, 1.0, 2000).reshape(-1, 1)

    peaks = compute_waveform_peaks(pcm, bucket_count=20)

    assert len(peaks) == 20


def test_compute_waveform_peaks_clamps_to_one_bucket_per_frame_on_a_short_signal() -> None:
    pcm = np.array([[0.1], [0.5], [-0.5]])

    peaks = compute_waveform_peaks(pcm, bucket_count=200)

    assert len(peaks) == 3


def test_compute_waveform_peaks_mixes_stereo_channels_to_mono() -> None:
    pcm = np.array([[1.0, -1.0], [1.0, -1.0]])

    peaks = compute_waveform_peaks(pcm, bucket_count=1)

    assert peaks[0].minimum == 0.0
    assert peaks[0].maximum == 0.0


def test_compute_waveform_peaks_reports_the_true_amplitude_range_per_bucket() -> None:
    pcm = np.array([[-0.75], [0.25], [0.9], [-0.1]])

    peaks = compute_waveform_peaks(pcm, bucket_count=1)

    assert peaks[0].minimum == -0.75
    assert peaks[0].maximum == 0.9


def test_trim_trailing_silence_removes_only_the_trailing_content_below_threshold() -> None:
    waveform = np.array([[0.5], [0.5], [0.01], [0.0]])

    trimmed = trim_trailing_silence(waveform, threshold=0.05)

    assert np.array_equal(trimmed, waveform[:2])


def test_trim_trailing_silence_leaves_leading_silence_untouched() -> None:
    waveform = np.array([[0.0], [0.0], [0.5], [0.5]])

    trimmed = trim_trailing_silence(waveform, threshold=0.05)

    assert np.array_equal(trimmed, waveform)


def test_trim_trailing_silence_preserves_content_exactly_at_the_threshold_boundary() -> None:
    waveform = np.array([[0.5], [0.05]])

    trimmed = trim_trailing_silence(waveform, threshold=0.05)

    assert trimmed.shape[0] == 1


def test_trim_trailing_silence_returns_an_empty_waveform_for_a_fully_silent_signal() -> None:
    waveform = np.zeros((5, 1))

    trimmed = trim_trailing_silence(waveform, threshold=0.05)

    assert trimmed.shape[0] == 0


def test_trim_trailing_silence_counts_a_frame_present_on_any_channel_as_content() -> None:
    waveform = np.array([[0.5, 0.0], [0.0, 0.5], [0.0, 0.0]])

    trimmed = trim_trailing_silence(waveform, threshold=0.05)

    assert trimmed.shape[0] == 2


def test_fold_to_mono_averages_the_channels_of_a_stereo_waveform() -> None:
    stereo = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])

    mono = fold_to_mono(stereo)

    assert np.allclose(mono, [0.5, 0.5, 0.5])


def test_fold_to_mono_passes_an_already_mono_signal_through_unchanged() -> None:
    mono = np.array([0.1, -0.2, 0.3])

    assert np.allclose(fold_to_mono(mono), mono)


def test_remove_dc_offset_centers_a_biased_signal_on_zero() -> None:
    biased = np.array([1.0, 2.0, 3.0])

    centered = remove_dc_offset(biased)

    assert np.isclose(centered.mean(), 0.0)


def test_remove_dc_offset_leaves_an_already_centered_signal_where_it_is() -> None:
    centered = np.array([-1.0, 0.0, 1.0])

    assert np.allclose(remove_dc_offset(centered), centered)


def test_resample_to_fraction_points_reproduces_exact_values_at_matching_points() -> None:
    values = np.array([0.0, 2.0, 4.0, 6.0, 8.0])

    resampled = resample_to_fraction_points(values, point_count=5)

    assert np.allclose(resampled, values)


def test_resample_to_fraction_points_interpolates_between_original_points() -> None:
    values = np.array([0.0, 10.0])

    resampled = resample_to_fraction_points(values, point_count=3)

    assert np.allclose(resampled, [0.0, 5.0, 10.0])


def test_resample_to_fraction_points_resamples_each_row_of_a_two_dimensional_series() -> None:
    """A spectrogram's frame axis is resampled while its frequency axis is preserved in place."""
    spectrogram = np.array([[0.0, 10.0], [4.0, 8.0]])

    resampled = resample_to_fraction_points(spectrogram, point_count=3, axis=1)

    assert resampled.shape == (2, 3)
    assert np.allclose(resampled, [[0.0, 5.0, 10.0], [4.0, 6.0, 8.0]])


def test_resample_to_fraction_points_holds_the_output_size_across_differing_input_lengths() -> None:
    short = resample_to_fraction_points(np.linspace(0.0, 1.0, 7), point_count=32)
    long = resample_to_fraction_points(np.linspace(0.0, 1.0, 4096), point_count=32)

    assert short.shape == long.shape == (32,)


def test_average_to_fraction_points_reads_a_single_frame_as_the_whole_span() -> None:
    """A retuned reading of a very short sample can analyze to one frame, which then covers everything."""
    single = np.array([[3.0], [5.0]])

    averaged = average_to_fraction_points(single, point_count=4, axis=1)

    assert np.isfinite(averaged).all()
    np.testing.assert_array_equal(averaged, [[3.0] * 4, [5.0] * 4])


def test_average_to_fraction_points_holds_a_constant_series_flat() -> None:
    averaged = average_to_fraction_points(np.full(400, 3.0), point_count=16)

    assert np.allclose(averaged, 3.0)


def test_average_to_fraction_points_carries_content_a_sampling_resample_would_step_over() -> None:
    """The guard this resampler exists for.

    A series alternating between two values carries no content at the rate a decimating sample
    reads it, so reading every nth point returns whichever value those points happen to land on.
    Averaging across each output point's span returns the mean the span actually holds.
    """
    alternating = np.tile([0.0, 1.0], 200)

    averaged = average_to_fraction_points(alternating, point_count=8)
    sampled = resample_to_fraction_points(alternating, point_count=8)

    assert np.allclose(averaged, 0.5, atol=0.05)
    assert float(np.abs(sampled - 0.5).max()) > 0.4


def test_average_to_fraction_points_interpolates_when_asked_for_more_points() -> None:
    averaged = average_to_fraction_points(np.array([0.0, 1.0]), point_count=3)

    assert averaged == pytest.approx([0.0, 0.5, 1.0])


def test_average_to_fraction_points_resamples_each_row_of_a_two_dimensional_series() -> None:
    spectrogram = np.stack([np.full(100, 1.0), np.full(100, 2.0)])

    averaged = average_to_fraction_points(spectrogram, point_count=5, axis=1)

    assert averaged.shape == (2, 5)
    assert np.allclose(averaged[0], 1.0)
    assert np.allclose(averaged[1], 2.0)


def test_triangular_weights_sum_to_one_for_every_target() -> None:
    weights = triangular_weights(
        source_positions=np.linspace(0.0, 1.0, 40),
        target_positions=np.linspace(0.0, 1.0, 7),
        half_widths=np.full(7, 1.0 / 6.0),
    )

    assert np.allclose(weights.sum(axis=1), 1.0)
