from __future__ import annotations

from pathlib import Path
from typing import Final, NamedTuple

import numpy as np
import soundfile
from numpy.typing import NDArray

from samplelibrary.sandbox.waveforms import SAMPLE_RATE, decaying, tonal_waveform

# A folder of plain audio files beside the modules, for `samplelibrary files`: two drums named for
# what they are, a stereo pad at a rate other than the nominal one, and a loop the sandbox's own
# exclusion leaves out.
SAMPLE_PACK_EXCLUSIONS: Final[tuple[str, ...]] = ("*loop*",)
PACK_PAD_RATE: Final[int] = 48000
PACK_DRUM_FRAMES: Final[int] = SAMPLE_RATE // 2
PACK_PAD_FRAMES: Final[int] = PACK_PAD_RATE * 2
PACK_SEED_OFFSET: Final[int] = 200


class PackFile(NamedTuple):
    """One file of the sandbox's sample pack: its frames as ``(frames, channels)``, its rate and its encoding."""

    waveform: NDArray[np.float64]
    rate: int
    subtype: str


def sample_pack() -> dict[str, PackFile]:
    """Every file of the sandbox's pack by its path inside the pack."""
    kick = decaying(tonal_waveform(PACK_DRUM_FRAMES, frequency=55.0, seed=PACK_SEED_OFFSET), rate=SAMPLE_RATE)
    noise = np.random.default_rng(PACK_SEED_OFFSET + 1).uniform(-1.0, 1.0, PACK_DRUM_FRAMES)
    pad = np.stack(
        [
            tonal_waveform(PACK_PAD_FRAMES, frequency=261.63, seed=PACK_SEED_OFFSET + 2),
            tonal_waveform(PACK_PAD_FRAMES, frequency=261.63, seed=PACK_SEED_OFFSET + 3),
        ],
        axis=1,
    )
    return {
        "Drums/Kick 01.wav": PackFile(kick.reshape(-1, 1), SAMPLE_RATE, "PCM_16"),
        "Drums/Snare 01.wav": PackFile(decaying(noise, rate=SAMPLE_RATE).reshape(-1, 1), SAMPLE_RATE, "PCM_24"),
        "Tonal/Pad C.flac": PackFile(0.5 * pad, PACK_PAD_RATE, "PCM_16"),
        "Loops/Drum Loop 01.wav": PackFile(np.tile(kick, 4).reshape(-1, 1), SAMPLE_RATE, "PCM_16"),
    }


def write_sample_pack(sample_pack_directory: Path) -> None:
    """Write every file of the pack under ``sample_pack_directory``, in the encoding each names."""
    for relative_path, pack_file in sample_pack().items():
        path = sample_pack_directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        soundfile.write(path, pack_file.waveform, pack_file.rate, subtype=pack_file.subtype)
