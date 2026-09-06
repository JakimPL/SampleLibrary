from __future__ import annotations

from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE

MFCC_COUNT: Final[int] = 13
DEFAULT_N_FFT: Final[int] = 2048
MINIMUM_SIGNAL_LENGTH: Final[int] = 512
SEGMENT_COUNT: Final[int] = 3
DEFAULT_DELTA_WIDTH: Final[int] = 9
MINIMUM_DELTA_WIDTH: Final[int] = 3
NO_ONSET_ATTACK_FRACTION: Final[float] = 0.0


class LibrosaFeatureExtractor:
    """Extracts a general-purpose timbral and temporal descriptor vector from a waveform with librosa.

    Concatenates each MFCC coefficient's mean and standard deviation across time, the mean and
    standard deviation of spectral centroid and spectral bandwidth, the mean zero-crossing rate,
    and the mean RMS energy -- a standard feature set for audio similarity and clustering, not
    tuned further than this starting point unless real results call for it. Three groups of
    temporal features sit alongside that whole-clip summary, so two sounds with the same overall
    timbre but a differently placed transient no longer produce the same vector: mean RMS and
    spectral centroid within each of ``SEGMENT_COUNT`` early/mid/late time segments, the duration-
    normalized fraction of the clip elapsed before its strongest onset, and the mean and standard
    deviation of each MFCC coefficient's frame-to-frame rate of change. Aggregating every group
    over time, rather than keeping a per-frame vector, is what keeps the output the same length
    whatever the input's own frame count; the waveform is padded up to a minimum working length
    first so a short tracker one-shot produces the same vector shape as a long loop, rather than
    failing library-internal windowing requirements.
    """

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        mono = _prepare_mono_signal(waveform)
        n_fft = min(DEFAULT_N_FFT, mono.shape[0])
        hop_length = n_fft // 4

        mfcc = librosa.feature.mfcc(y=mono, sr=NOMINAL_WAV_RATE, n_mfcc=MFCC_COUNT, n_fft=n_fft, hop_length=hop_length)
        centroid = librosa.feature.spectral_centroid(y=mono, sr=NOMINAL_WAV_RATE, n_fft=n_fft, hop_length=hop_length)
        bandwidth = librosa.feature.spectral_bandwidth(y=mono, sr=NOMINAL_WAV_RATE, n_fft=n_fft, hop_length=hop_length)
        zero_crossing_rate = librosa.feature.zero_crossing_rate(mono, frame_length=n_fft, hop_length=hop_length)
        rms = librosa.feature.rms(y=mono, frame_length=n_fft, hop_length=hop_length)

        return np.concatenate(
            [
                mfcc.mean(axis=1),
                mfcc.std(axis=1),
                centroid.mean(axis=1),
                centroid.std(axis=1),
                bandwidth.mean(axis=1),
                bandwidth.std(axis=1),
                zero_crossing_rate.mean(axis=1),
                rms.mean(axis=1),
                _segment_wise_means(rms, centroid),
                [_attack_time_fraction(mono, sample_rate=NOMINAL_WAV_RATE, n_fft=n_fft, hop_length=hop_length)],
                _delta_mfcc_statistics(mfcc),
            ]
        )


def _prepare_mono_signal(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    mono = waveform.mean(axis=1) if waveform.ndim > 1 else waveform
    if mono.shape[0] < MINIMUM_SIGNAL_LENGTH:
        return np.pad(mono, (0, MINIMUM_SIGNAL_LENGTH - mono.shape[0]))
    return mono


def _segment_wise_means(rms: NDArray[np.float64], centroid: NDArray[np.float64]) -> NDArray[np.float64]:
    """Mean RMS and mean spectral centroid within each of ``SEGMENT_COUNT`` equal time segments.

    Splitting the frame axis into early/mid/late segments before averaging keeps a transient's
    position in time visible in the resulting vector, where the whole-clip mean this extractor
    already reports collapses that position away entirely.
    """
    rms_segments = np.array_split(rms[0], SEGMENT_COUNT)
    centroid_segments = np.array_split(centroid[0], SEGMENT_COUNT)
    return np.array([segment.mean() for segment in rms_segments] + [segment.mean() for segment in centroid_segments])


def _attack_time_fraction(mono: NDArray[np.float64], *, sample_rate: int, n_fft: int, hop_length: int) -> float:
    """Fraction of the clip's duration elapsed before its strongest onset, in ``[0, 1]``.

    Normalizing by duration keeps the value comparable across samples of different lengths: a
    fast attack lands near 0.0 whatever the clip's total length, and a backloaded or reversed
    sound reports a fraction near 1.0. A clip with no detected onset reports
    ``NO_ONSET_ATTACK_FRACTION``, treating an attack right at the start as the least presumptuous
    default when there is nothing to measure.
    """
    onset_envelope = librosa.onset.onset_strength(y=mono, sr=sample_rate, n_fft=n_fft, hop_length=hop_length)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_envelope, sr=sample_rate, hop_length=hop_length)
    if onset_frames.size == 0:
        return NO_ONSET_ATTACK_FRACTION
    onset_time = librosa.frames_to_time(onset_frames[0], sr=sample_rate, hop_length=hop_length)
    total_duration = mono.shape[0] / sample_rate
    return float(np.clip(onset_time / total_duration, 0.0, 1.0))


def _delta_mfcc_statistics(mfcc: NDArray[np.float64]) -> NDArray[np.float64]:
    """Mean and standard deviation of each MFCC coefficient's frame-to-frame rate of change.

    Captures how quickly timbre moves over time, separating sounds with similar average spectral
    content but different articulation -- a plucked string's fast initial change against a bowed
    string's slow, sustained one. A clip too short for ``DEFAULT_DELTA_WIDTH`` frames falls back to
    the largest odd window its frame count allows, and one shorter than ``MINIMUM_DELTA_WIDTH``
    reports zero change throughout, since no meaningful rate of change is measurable from it.
    """
    frame_count = mfcc.shape[1]
    if frame_count < MINIMUM_DELTA_WIDTH:
        return np.zeros(2 * MFCC_COUNT)
    width = min(DEFAULT_DELTA_WIDTH, frame_count if frame_count % 2 == 1 else frame_count - 1)
    delta = librosa.feature.delta(mfcc, width=width)
    return np.concatenate([delta.mean(axis=1), delta.std(axis=1)])
