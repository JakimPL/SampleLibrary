from __future__ import annotations

from collections.abc import Callable
from typing import Final, NamedTuple

import numpy as np
from numpy.typing import NDArray

from samplelibrary.sandbox.sample_pack import PackFile
from samplelibrary.sandbox.waveforms import SAMPLE_RATE, decaying, tonal_waveform

ONE_SHOT_COUNT: Final[int] = 300
ONE_SHOTS_DIRECTORY_NAME: Final[str] = "One-shots"
ONE_SHOT_SEED_OFFSET: Final[int] = 1000
# Every one-shot is at least this long, which keeps it inside the draws a codec is fitted over.
ONE_SHOT_FRAMES: Final[int] = SAMPLE_RATE // 2
SUSTAINED_FRAMES: Final[int] = SAMPLE_RATE


class SoundKind(NamedTuple):
    """One kind of one-shot: its folder, the label a person gives it, and how its sound is made."""

    folder: str
    label: str
    sound: Callable[[int], NDArray[np.float64]]


def _struck(low_hz: float, high_hz: float) -> Callable[[int], NDArray[np.float64]]:
    def sound(seed: int) -> NDArray[np.float64]:
        frequency = np.random.default_rng(seed).uniform(low_hz, high_hz)
        return decaying(tonal_waveform(ONE_SHOT_FRAMES, frequency=frequency, seed=seed), rate=SAMPLE_RATE)

    return sound


def _sustained(low_hz: float, high_hz: float) -> Callable[[int], NDArray[np.float64]]:
    def sound(seed: int) -> NDArray[np.float64]:
        frequency = np.random.default_rng(seed).uniform(low_hz, high_hz)
        return 0.6 * tonal_waveform(SUSTAINED_FRAMES, frequency=frequency, seed=seed)

    return sound


def _noise(frames: int) -> Callable[[int], NDArray[np.float64]]:
    def sound(seed: int) -> NDArray[np.float64]:
        return decaying(np.random.default_rng(seed).uniform(-1.0, 1.0, frames), rate=SAMPLE_RATE)

    return sound


SOUND_KINDS: Final[tuple[SoundKind, ...]] = (
    SoundKind("Kicks", "BASS DRUM", _struck(40.0, 80.0)),
    SoundKind("Snares", "SNARE", _noise(ONE_SHOT_FRAMES)),
    SoundKind("Hats", "HI-HAT: CLOSED", _noise(ONE_SHOT_FRAMES)),
    SoundKind("Toms", "TOM", _struck(90.0, 220.0)),
    SoundKind("Bass", "BASS", _sustained(40.0, 110.0)),
    SoundKind("Leads", "LEAD", _sustained(220.0, 880.0)),
    SoundKind("Plucks", "PLUCK", _struck(300.0, 1200.0)),
    SoundKind("Pads", "PAD", _sustained(110.0, 440.0)),
    SoundKind("Bells", "BELL", _struck(800.0, 2400.0)),
    SoundKind("FX", "FX", _noise(SUSTAINED_FRAMES)),
)


def one_shots(count: int = ONE_SHOT_COUNT) -> dict[str, PackFile]:
    """A folder of synthetic one-shots, ``count`` in all, taking every kind in turn.

    Each one-shot is seeded on its own, so no two relate to each other and the catalog they fill
    holds enough samples to train, fit and score every model the pipeline builds.
    """
    shots: dict[str, PackFile] = {}
    for index in range(count):
        kind = SOUND_KINDS[index % len(SOUND_KINDS)]
        waveform = kind.sound(ONE_SHOT_SEED_OFFSET + index)
        relative_path = f"{ONE_SHOTS_DIRECTORY_NAME}/{kind.folder}/{kind.folder} {index:03d}.wav"
        shots[relative_path] = PackFile(waveform.reshape(-1, 1), SAMPLE_RATE, "PCM_16")
    return shots


def labeled_one_shots() -> dict[str, str]:
    """The first one-shot of every kind, with the label a person gives it."""
    return {
        f"{ONE_SHOTS_DIRECTORY_NAME}/{kind.folder}/{kind.folder} {index:03d}.wav": kind.label
        for index, kind in enumerate(SOUND_KINDS)
    }
