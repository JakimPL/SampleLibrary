from __future__ import annotations

import numpy as np

from samplecore.waveform import (
    compute_waveform_peaks,
    fold_to_mono,
    remove_dc_offset,
    resample_to_fraction_points,
    trim_trailing_silence,
)


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
