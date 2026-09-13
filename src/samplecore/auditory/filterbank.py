from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.auditory.framing import convolution_fft_size

ERB_SCALE_SLOPE: Final[float] = 21.4
ERB_FREQUENCY_FACTOR_PER_HZ: Final[float] = 4.37e-3
ERB_BANDWIDTH_MINIMUM_HZ: Final[float] = 24.7
GAMMATONE_ORDER: Final[int] = 4
GAMMATONE_BANDWIDTH_FACTOR: Final[float] = 1.019
GAMMATONE_KERNEL_SECONDS: Final[float] = 0.08
DEFAULT_CHANNEL_COUNT: Final[int] = 24
DEFAULT_LOWEST_CENTER_HZ: Final[float] = 50.0
DEFAULT_HIGHEST_CENTER_HZ: Final[float] = 16000.0
HIGHEST_CENTER_NYQUIST_FRACTION: Final[float] = 0.4


def erb_rate(frequency_hz: NDArray[np.float64]) -> NDArray[np.float64]:
    """How many equivalent rectangular bandwidths lie below each frequency (Glasberg and Moore, 1990)."""
    rate: NDArray[np.float64] = ERB_SCALE_SLOPE * np.log10(ERB_FREQUENCY_FACTOR_PER_HZ * frequency_hz + 1.0)
    return rate


def erb_frequency_hz(rate: NDArray[np.float64]) -> NDArray[np.float64]:
    """The frequency sitting `rate` equivalent rectangular bandwidths up the scale, inverting `erb_rate`."""
    frequency: NDArray[np.float64] = (10.0 ** (rate / ERB_SCALE_SLOPE) - 1.0) / ERB_FREQUENCY_FACTOR_PER_HZ
    return frequency


def erb_bandwidth_hz(frequency_hz: NDArray[np.float64]) -> NDArray[np.float64]:
    """The equivalent rectangular bandwidth of the auditory filter centered on each frequency."""
    bandwidth: NDArray[np.float64] = ERB_BANDWIDTH_MINIMUM_HZ * (ERB_FREQUENCY_FACTOR_PER_HZ * frequency_hz + 1.0)
    return bandwidth


def erb_spaced_centers(*, lowest_hz: float, highest_hz: float, channel_count: int) -> NDArray[np.float64]:
    """`channel_count` center frequencies from `lowest_hz` to `highest_hz`, evenly spaced on the ERB scale."""
    edges = erb_rate(np.array([lowest_hz, highest_hz]))
    return erb_frequency_hz(np.linspace(edges[0], edges[1], channel_count))


@dataclass(frozen=True)
class GammatoneBank:
    """A bank of gammatone filters as finite analytic kernels, one row per channel, lowest first.

    Each kernel is the complex gammatone ``t^(order-1) e^(-2 pi b t) e^(j 2 pi f t)`` of Patterson
    et al. (1992), whose bandwidth `b` is 1.019 times the channel's equivalent rectangular
    bandwidth. Convolving a real signal with it yields the channel's analytic signal, so the
    magnitude of that output is the channel's envelope; the kernel is scaled so a unit cosine at
    the center frequency reads an envelope of one. Cosine and sine parts travel separately so an
    applier working in real arithmetic reads them as they are.
    """

    sample_rate_hz: int
    center_frequencies_hz: NDArray[np.float64]
    kernel_cosine: NDArray[np.float64]  # (channels, taps)
    kernel_sine: NDArray[np.float64]  # (channels, taps)

    @property
    def channel_count(self) -> int:
        return int(self.center_frequencies_hz.shape[0])

    @property
    def kernel_length(self) -> int:
        return int(self.kernel_cosine.shape[1])

    @property
    def kernel(self) -> NDArray[np.complex128]:
        return self.kernel_cosine + 1j * self.kernel_sine


@cache
def design_gammatone_bank(
    *,
    sample_rate_hz: int,
    channel_count: int = DEFAULT_CHANNEL_COUNT,
    lowest_center_hz: float = DEFAULT_LOWEST_CENTER_HZ,
    highest_center_hz: float = DEFAULT_HIGHEST_CENTER_HZ,
) -> GammatoneBank:
    """Design the bank for one sample rate, holding its top channel well below the Nyquist frequency.

    The highest center is capped at `HIGHEST_CENTER_NYQUIST_FRACTION` of the rate, so a bank
    designed for a low playback rate keeps its top channel's skirt inside the band the signal
    carries. The kernel spans `GAMMATONE_KERNEL_SECONDS`, which holds the lowest channel's
    envelope until it has decayed by more than sixty decibels.

    Raises:
        ValueError: the rate leaves no room between the lowest center and the capped highest one.
    """
    highest_hz = min(highest_center_hz, HIGHEST_CENTER_NYQUIST_FRACTION * sample_rate_hz)
    if lowest_center_hz >= highest_hz:
        raise ValueError(
            f"a bank at {sample_rate_hz} Hz would place its highest center at {highest_hz:.0f} Hz, "
            f"at or below the lowest center of {lowest_center_hz:.0f} Hz"
        )

    centers = erb_spaced_centers(lowest_hz=lowest_center_hz, highest_hz=highest_hz, channel_count=channel_count)
    bandwidths = GAMMATONE_BANDWIDTH_FACTOR * erb_bandwidth_hz(centers)
    times = np.arange(int(round(GAMMATONE_KERNEL_SECONDS * sample_rate_hz))) / sample_rate_hz
    envelope = times[None, :] ** (GAMMATONE_ORDER - 1) * np.exp(-2.0 * np.pi * bandwidths[:, None] * times[None, :])
    carrier = np.exp(2j * np.pi * centers[:, None] * times[None, :])
    kernel = 2.0 * envelope * carrier / envelope.sum(axis=1, keepdims=True)
    return GammatoneBank(
        sample_rate_hz=sample_rate_hz,
        center_frequencies_hz=centers,
        kernel_cosine=np.ascontiguousarray(kernel.real),
        kernel_sine=np.ascontiguousarray(kernel.imag),
    )


def analytic_subbands(waveform: NDArray[np.float64], *, bank: GammatoneBank) -> NDArray[np.complex128]:
    """Each channel's analytic signal over the waveform, shaped ``(channels, samples)``.

    The convolution runs causally through one transform sized by `convolution_fft_size` and is
    trimmed to the waveform's own length, so every channel keeps its own group delay and two
    waveforms read through one bank line up sample for sample.
    """
    fft_size = convolution_fft_size(waveform.shape[0], bank.kernel_length)
    spectrum = np.fft.fft(waveform, n=fft_size)
    kernel_spectrum = np.fft.fft(bank.kernel, n=fft_size, axis=-1)
    subbands: NDArray[np.complex128] = np.fft.ifft(spectrum[None, :] * kernel_spectrum, axis=-1)[:, : waveform.shape[0]]
    return subbands
