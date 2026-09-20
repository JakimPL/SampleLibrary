from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel, Field, JsonValue

from samplecore.models.base import FROZEN
from samplecore.storage.atomic import write_atomically
from samplemorph.canonicalizers.common import PreparedMono
from samplemorph.coordinates.frames import FrameAnalysis, constant_q_frames
from samplemorph.coordinates.pitch_head.network import PitchNetwork
from samplemorph.coordinates.pitch_head.readout import read_sound
from samplemorph.coordinates.pitch_head.shape import PitchHeadShape
from samplemorph.coordinates.readers import PitchReading

DESCRIPTION_KEY: Final[str] = "description"
NETWORK_KEY: Final[str] = "network"
NO_CALIBRATION_SEMITONES: Final[float] = 0.0


class PitchHeadDescription(BaseModel):
    """What a trained pitch head is and where it came from, recorded beside its weights.

    `analysis` is the frame analysis every sound it reads must be read through, and `cache` names
    the frame cache it was taught on. `calibration_semitones` is where its lowest output bin sounds,
    read from plain harmonic tones after training, and `trusted_reliability` the reading a route
    glides by. `validation_hashes` are the samples it was judged on and never taught, and
    `parameters` what its run was asked to do.
    """

    model_config = FROZEN

    name: str
    cache: str
    analysis: FrameAnalysis
    shape: PitchHeadShape
    calibration_semitones: float
    trusted_reliability: float = Field(ge=0.0, le=1.0)
    random_seed: int
    epochs: int
    trained_sample_count: int
    best_validation_error: float
    validation_hashes: tuple[str, ...]
    parameters: dict[str, str]


@dataclass(frozen=True)
class StoredPitchHead:
    """A trained pitch head, which reads a sound's pitch the way every other reader does.

    Each of a sound's frames is read on its own into a pitch and the mass standing on it; the
    sound's pitch is the median of them weighted by that mass, and its reliability is how gathered
    the frames' answers are times how far they agree with the median. A sound with no frame that
    sounds has no pitch to read.
    """

    network: PitchNetwork
    description: PitchHeadDescription
    device: torch.device

    @property
    def name(self) -> str:
        return self.description.name

    @property
    def trusted_reliability(self) -> float:
        return self.description.trusted_reliability

    def describe(self) -> dict[str, JsonValue]:
        return {"reader": self.name, **self.description.model_dump(mode="json")}

    def read(self, mono: PreparedMono) -> PitchReading | None:
        frames = constant_q_frames(mono, analysis=self.description.analysis)
        if frames.shape[0] == 0:
            return None
        return self.read_frames(frames)

    def read_frames(self, frames: NDArray[np.float32]) -> PitchReading:
        """The pitch a sound's kept frames sound. Shape: `frames` is ``(frames, bands)``."""
        kept = torch.from_numpy(np.ascontiguousarray(frames))[None].to(self.device)
        with torch.no_grad():
            distributions = self.network(kept[0])[None]
            readout = read_sound(
                distributions,
                valid=torch.ones(distributions.shape[:2], device=self.device),
                reach_bins=self.description.shape.readout_reach_bins,
            )
        return PitchReading(
            semitones=self.semitones_of(float(readout.bins.item())),
            reliability=float(readout.reliability.item()),
        )

    def semitones_of(self, bins: float) -> float:
        """Where an output bin sounds, in semitones from the reference frequency, once the head is calibrated."""
        return bins / self.description.shape.bins_per_semitone + self.description.calibration_semitones


def save_pitch_head(path: Path, *, network: PitchNetwork, description: PitchHeadDescription) -> None:
    """Write a head beside the description that rebuilds it, in place whole."""
    stored = {DESCRIPTION_KEY: description.model_dump_json(), NETWORK_KEY: network.state_dict()}
    write_atomically(path, lambda stream: torch.save(stored, stream))


def load_pitch_head(path: Path, *, device: torch.device) -> StoredPitchHead:
    """Rebuild a trained pitch head on `device`, ready to read.

    Raises:
        FileNotFoundError: no pitch head is stored at that path.
    """
    if not path.exists():
        raise FileNotFoundError(f"no pitch head is stored at {path}")

    stored = torch.load(path, map_location=device, weights_only=True)
    description = PitchHeadDescription.model_validate_json(str(stored[DESCRIPTION_KEY]))
    network = PitchNetwork(description.shape).to(device)
    network.load_state_dict(stored[NETWORK_KEY])
    network.eval()
    return StoredPitchHead(network=network, description=description, device=device)


def calibrated(head: StoredPitchHead, *, semitones: float) -> StoredPitchHead:
    """The same head reading `semitones` higher, which is how the offset read from known tones is set."""
    return StoredPitchHead(
        network=head.network,
        description=head.description.model_copy(update={"calibration_semitones": semitones}),
        device=head.device,
    )
