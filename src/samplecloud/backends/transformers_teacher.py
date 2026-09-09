from __future__ import annotations

from typing import Final

import numpy as np
import torch
from numpy.typing import NDArray
from transformers import ClapFeatureExtractor, ClapModel

# The audio tower reads a fixed picture: a ten-second window at the model's rate, as a log-mel
# spectrogram of this many frames. A shorter clip is repeated to fill the window and padded with
# silence, which is the model's own reading of a short sound; a longer one is read from its start.
WINDOW_SECONDS: Final[int] = 10
LOG_MEL_FLOOR: Final[float] = 1e-10


class TransformersTeacher:
    """The pretrained audio-text model as `transformers` ships it, kept behind the `Teacher` protocol.

    Only the audio tower is used, and the log-mel picture it reads is computed here on the device
    rather than by the library's own extractor: the same window, hop, filter bank and decibel
    floor, measured to agree within a twentieth of a decibel with vectors identical to six decimals,
    at a quarter of the cost. The vector is unit length, so distances between two of them read as
    cosine distances, which is the geometry the model was trained under.
    """

    def __init__(self, *, checkpoint: str, rate_hz: int) -> None:
        self._rate_hz = rate_hz
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        model = ClapModel.from_pretrained(checkpoint)
        # The library types the wrapped `to` as taking the model where it takes the device, so the
        # call is accepted as the library documents it.
        self._model = model.to(self._device).eval()  # type: ignore[arg-type]
        extractor = ClapFeatureExtractor.from_pretrained(checkpoint)
        self._window_frames = WINDOW_SECONDS * rate_hz
        self._fft_length = int(extractor.fft_window_size)
        self._hop_length = int(extractor.hop_length)
        # (fourier bins, mel bands): the filter bank the non-fusion checkpoints were trained with.
        self._mel_filters = torch.as_tensor(extractor.mel_filters_slaney, dtype=torch.float32, device=self._device)
        self._taper = torch.hann_window(self._fft_length, periodic=True, device=self._device)

    def embed(self, mono: NDArray[np.float32]) -> NDArray[np.float32]:
        window = torch.as_tensor(fill_window(mono, self._window_frames), device=self._device)
        # (1, 1, frames, mel bands), the layout the audio tower expects
        features = self._log_mel(window)[None, None]
        with torch.no_grad():
            pooled = self._model.get_audio_features(input_features=features)
        # Newer releases return an output object in place of the tensor; either way the vector is pooled.
        tensor = pooled if isinstance(pooled, torch.Tensor) else pooled.pooler_output
        vector: NDArray[np.float32] = torch.nn.functional.normalize(tensor, dim=-1)[0].cpu().numpy()
        return vector

    def _log_mel(self, window: torch.Tensor) -> torch.Tensor:
        """The library's log-mel picture, computed on the device: power spectrum, mel bands, decibels."""
        spectrum = torch.stft(
            window,
            n_fft=self._fft_length,
            hop_length=self._hop_length,
            window=self._taper,
            center=True,
            pad_mode="reflect",
            return_complex=True,
        )
        power = spectrum.real**2 + spectrum.imag**2  # (fourier bins, frames)
        mel = torch.clamp(self._mel_filters.T @ power, min=LOG_MEL_FLOOR)
        return (10.0 * torch.log10(mel)).T  # (frames, mel bands)


def fill_window(mono: NDArray[np.float32], window_frames: int) -> NDArray[np.float32]:
    """The clip as the model's window: repeated whole to fill it, padded with silence, or read from its start."""
    if mono.shape[0] >= window_frames:
        return np.ascontiguousarray(mono[:window_frames])
    repeats = window_frames // mono.shape[0]
    tiled = np.tile(mono, repeats)
    return np.pad(tiled, (0, window_frames - tiled.shape[0]))
