from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import librosa
import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplemorph.canonicalizers.linear_axis import onto_linear_axis
from samplemorph.images import AnalysisSpectrogram
from samplemorph.vocoders.phase_model import PhaseModel, PhaseModelShape

PHASE_MODEL_SUFFIX: Final[str] = ".pt"
DEFAULT_PHASE_MODEL_NAME: Final[str] = "phase"


class PhaseModelDescription(BaseModel):
    """What a fitted phase model is, recorded beside its weights so a file explains itself."""

    model_config = FROZEN

    canonicalizer: str
    bin_count: int
    frames_per_turn: int
    channels: int
    kernel_size: int
    dilations: tuple[int, ...]
    fft_length: int
    hop_length: int
    epochs: int
    trained_sample_count: int
    best_validation_loss: float


@dataclass(frozen=True)
class LearnedPhaseVocoder:
    """Estimates the phase a magnitude lost, from a model taught what phase such magnitudes carry.

    Griffin-Lim searches for a phase consistent with the magnitude it is given, and the magnitude a
    canonical grid produces is a smoothed reading that no signal has exactly, so the search settles
    on an artifact whatever resolution it runs at. A model trained on pairs of this pipeline's own
    magnitudes and the phase they came from answers a different question: what phase does a
    magnitude of this kind carry. That question has an answer in the corpus.
    """

    model: PhaseModel
    description: PhaseModelDescription
    device: torch.device

    def synthesize(self, spectrogram: AnalysisSpectrogram) -> NDArray[np.float64]:
        """Read the magnitude onto the Fourier grid, ask for its phase, and return the frames."""
        linear = onto_linear_axis(spectrogram.magnitude, geometry=spectrogram.geometry)
        magnitude = torch.from_numpy(linear.astype(np.float32)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            phase = self.model(magnitude)
        spectrum = torch.complex(magnitude * phase[:, 0], magnitude * phase[:, 1]).squeeze(0)
        waveform: NDArray[np.float64] = librosa.istft(
            spectrum.cpu().numpy(),
            n_fft=spectrogram.geometry.fft_length,
            hop_length=spectrogram.geometry.hop_length,
            length=spectrogram.frame_count,
        ).astype(np.float64)
        return waveform


def phase_model_path(library_root: Path, *, name: str = DEFAULT_PHASE_MODEL_NAME) -> Path:
    """Where a fitted phase model is written, under the configured library root rather than the repo."""
    return library_root / "models" / f"{name}{PHASE_MODEL_SUFFIX}"


def save_phase_model(path: Path, model: PhaseModel, description: PhaseModelDescription) -> None:
    """Write the weights beside the description that says how to rebuild the network around them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"description": description.model_dump_json(), "state": model.state_dict()}, path)


def load_phase_model(path: Path, *, device: torch.device) -> LearnedPhaseVocoder:
    """Rebuild a fitted phase model and the vocoder that speaks for it.

    Raises:
        FileNotFoundError: no model is stored at that path.
    """
    if not path.exists():
        raise FileNotFoundError(f"no phase model is stored at {path}")

    stored = torch.load(path, map_location=device, weights_only=True)
    description = PhaseModelDescription.model_validate_json(str(stored["description"]))
    shape = PhaseModelShape(
        bin_count=description.bin_count,
        frames_per_turn=description.frames_per_turn,
        channels=description.channels,
        kernel_size=description.kernel_size,
        dilations=tuple(description.dilations),
    )
    model = PhaseModel(shape).to(device)
    model.load_state_dict(stored["state"])
    model.eval()
    return LearnedPhaseVocoder(model=model, description=description, device=device)
