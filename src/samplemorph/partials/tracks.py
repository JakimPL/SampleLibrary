from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.partials.peaks import SpectralPeaks
from samplemorph.partials.settings import PartialSettings

CENTS_PER_OCTAVE: Final[float] = 100.0 * SEMITONES_PER_OCTAVE


@dataclass(frozen=True)
class PartialTracks:
    """Partials followed from frame to frame, each a frequency and an amplitude over the analysis frames.

    A track's amplitude is zero on every frame it does not sound, and its frequency there holds the
    nearest frequency it sounded at, so a track reads continuously wherever it is looked up. Frames
    are `hop_length` samples apart at `rate_hz`. Shapes: both arrays are ``(tracks, frames)``.
    """

    frequency_hz: NDArray[np.float32]
    amplitude: NDArray[np.float32]
    hop_length: int
    rate_hz: float

    @property
    def track_count(self) -> int:
        return int(self.amplitude.shape[0])

    @property
    def frame_count(self) -> int:
        return int(self.amplitude.shape[1])

    @property
    def sounding(self) -> NDArray[np.bool_]:
        sounding: NDArray[np.bool_] = self.amplitude > 0.0
        return sounding


@dataclass
class _OpenTrack:
    frames: list[int] = field(default_factory=list)
    frequency_hz: list[float] = field(default_factory=list)
    amplitude: list[float] = field(default_factory=list)

    @property
    def last_frame(self) -> int:
        return self.frames[-1]

    @property
    def last_frequency_hz(self) -> float:
        return self.frequency_hz[-1]


def track_peaks(peaks: SpectralPeaks, *, hop_length: int, rate_hz: float, settings: PartialSettings) -> PartialTracks:
    """Join peaks into partials, frame by frame.

    A track and a peak join when each is the other's nearest and the peak lies within the settings'
    continuation limit of the track's last frequency, a limit that widens with the frames the track
    has been silent; a track silent longer than `gap_frames` closes, and every peak left unjoined opens
    a track. Mutual nearness keeps two close partials on their own tracks. Gaps a track bridged are
    filled by straight lines through frequency and amplitude, and a track shorter than
    `minimum_track_seconds` is dropped.
    """
    open_tracks: list[_OpenTrack] = []
    closed: list[_OpenTrack] = []
    frame_starts = np.searchsorted(peaks.frames, np.arange(peaks.frame_count + 1))
    for frame in range(peaks.frame_count):
        start, end = frame_starts[frame], frame_starts[frame + 1]
        frequencies, amplitudes = peaks.frequency_hz[start:end], peaks.amplitude[start:end]
        still_open = [track for track in open_tracks if frame - track.last_frame <= settings.gap_frames + 1]
        closed.extend(track for track in open_tracks if frame - track.last_frame > settings.gap_frames + 1)
        silent_seconds = np.array([frame - track.last_frame for track in still_open]) * hop_length / rate_hz
        joined = _mutual_nearest(
            np.array([track.last_frequency_hz for track in still_open]),
            frequencies,
            cents_limits=settings.continuation_cents_per_second * silent_seconds,
            hertz_limit=settings.continuation_floor_hz,
        )
        for track_index, peak_index in joined:
            track = still_open[track_index]
            track.frames.append(frame)
            track.frequency_hz.append(float(frequencies[peak_index]))
            track.amplitude.append(float(amplitudes[peak_index]))
        taken = {peak_index for _, peak_index in joined}
        opened = [
            _OpenTrack(frames=[frame], frequency_hz=[float(frequencies[index])], amplitude=[float(amplitudes[index])])
            for index in range(frequencies.shape[0])
            if index not in taken
        ]
        open_tracks = still_open + opened
    minimum_frames = settings.minimum_track_seconds * rate_hz / hop_length
    kept = [track for track in (*closed, *open_tracks) if track.last_frame - track.frames[0] + 1 >= minimum_frames]
    return _dense(kept, frame_count=peaks.frame_count, hop_length=hop_length, rate_hz=rate_hz)


def _mutual_nearest(
    last_frequencies: NDArray[np.float64],
    frequencies: NDArray[np.float64],
    *,
    cents_limits: NDArray[np.float64],
    hertz_limit: float,
) -> list[tuple[int, int]]:
    """Every track and peak that are each other's nearest in pitch, and close enough to join, as index pairs."""
    if last_frequencies.shape[0] == 0 or frequencies.shape[0] == 0:
        return []
    cents = np.abs(CENTS_PER_OCTAVE * np.log2(frequencies[None, :] / last_frequencies[:, None]))
    nearest_peak = cents.argmin(axis=1)
    nearest_track = cents.argmin(axis=0)
    tracks = np.arange(last_frequencies.shape[0])
    mutual = nearest_track[nearest_peak] == tracks
    close = (cents[tracks, nearest_peak] <= cents_limits) | (
        np.abs(frequencies[nearest_peak] - last_frequencies) <= hertz_limit
    )
    return [(int(track), int(nearest_peak[track])) for track in np.flatnonzero(mutual & close)]


def _dense(tracks: list[_OpenTrack], *, frame_count: int, hop_length: int, rate_hz: float) -> PartialTracks:
    frequency = np.zeros((len(tracks), frame_count), dtype=np.float32)
    amplitude = np.zeros((len(tracks), frame_count), dtype=np.float32)
    for index, track in enumerate(
        sorted(tracks, key=lambda open_track: (open_track.frames[0], open_track.frequency_hz[0]))
    ):
        frames = np.arange(track.frames[0], track.last_frame + 1)
        amplitude[index, frames] = np.interp(frames, track.frames, track.amplitude)
        frequency[index] = np.interp(np.arange(frame_count), track.frames, track.frequency_hz)
    return PartialTracks(frequency_hz=frequency, amplitude=amplitude, hop_length=hop_length, rate_hz=rate_hz)
