from __future__ import annotations

import numpy as np

from samplecore.waveform import compute_waveform_peaks


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
