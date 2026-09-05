from __future__ import annotations

import numpy as np

from samplecore.waveform import compute_waveform_peaks, trim_trailing_silence


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
