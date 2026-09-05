from __future__ import annotations

from typing import Final

import librosa
import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE

MFCC_COUNT: Final[int] = 13
DEFAULT_N_FFT: Final[int] = 2048
MINIMUM_SIGNAL_LENGTH: Final[int] = 512


class LibrosaFeatureExtractor:
    """Extracts a general-purpose timbral descriptor vector from a waveform with librosa.

    Concatenates each MFCC coefficient's mean and standard deviation across time, plus the mean
    and standard deviation of spectral centroid and spectral bandwidth, the mean zero-crossing
    rate, and the mean RMS energy -- a standard feature set for audio similarity and clustering,
    not tuned further than this starting point unless real results call for it. Aggregating over
    time, rather than keeping a per-frame vector, is what keeps the output the same length
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
            ]
        )


def _prepare_mono_signal(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    mono = waveform.mean(axis=1) if waveform.ndim > 1 else waveform
    if mono.shape[0] < MINIMUM_SIGNAL_LENGTH:
        return np.pad(mono, (0, MINIMUM_SIGNAL_LENGTH - mono.shape[0]))
    return mono
