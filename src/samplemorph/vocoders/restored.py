from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplemorph.canonicalizers.linear_axis import onto_linear_axis
from samplemorph.geometry import LogFrequencyGeometry
from samplemorph.images import AnalysisSpectrogram
from samplemorph.vocoders.levels import peak_level
from samplemorph.vocoders.pghi import gaussian_log_frequency, integrate_and_synthesize
from samplemorph.vocoders.restorer_model import Restorer, RestorerShape, compress, expand

RESTORER_SUFFIX: Final[str] = ".pt"
DEFAULT_RESTORER_NAME: Final[str] = "restorer"


class RestorerDescription(BaseModel):
    """What a fitted restorer is, recorded beside its weights so a file explains itself.

    The geometry travels with the model because the smoothing a restorer learned to undo is the
    band averaging of one analysis: the same network reading a magnitude from another grid would
    be putting back structure that grid never removed.
    """

    model_config = FROZEN

    canonicalizer: str
    geometry: LogFrequencyGeometry
    channels: int
    kernel_size: int
    dilations: tuple[int, ...]
    epochs: int
    trained_sample_count: int
    best_validation_loss: float
    least_squares_validation_loss: float


@dataclass(frozen=True)
class RestoredPghiVocoder:
    """Puts back what the band averaging removed, then integrates the phase of the result.

    The least-squares reading of a grid is the best magnitude the bands alone determine, and on
    every kind of sound it still lacks the fine structure listening misses most -- a slap bass's
    transient, a riser's own modulation. The restorer states that structure from what the corpus
    says such spectra carry, and gradient heap integration then reads a phase for a magnitude
    much nearer a real analysis. Listening on the candidate set passed this path where the
    least-squares reading alone failed two probes.
    """

    model: Restorer
    description: RestorerDescription
    device: torch.device

    def synthesize(self, spectrogram: AnalysisSpectrogram) -> NDArray[np.float64]:
        """Read the magnitude onto the Fourier grid, restore it, integrate its phase and return the frames.

        Raises:
            ValueError: the spectrogram was analyzed on a geometry other than the one the restorer was taught on.
        """
        geometry = gaussian_log_frequency(spectrogram.geometry)
        if not same_analysis(geometry, self.description.geometry):
            raise ValueError(
                "this restorer was taught the least-squares reading of a "
                f"{self.description.geometry.fft_length}/{self.description.geometry.hop_length} analysis at "
                f"{self.description.geometry.bins_per_octave} bands per octave, and this spectrogram is a "
                f"{geometry.fft_length}/{geometry.hop_length} one at {geometry.bins_per_octave}"
            )

        restored = self._restore(onto_linear_axis(spectrogram.magnitude, geometry=geometry))
        return integrate_and_synthesize(restored, geometry=geometry, frame_count=spectrogram.frame_count)

    def _restore(self, magnitude: NDArray[np.float64]) -> NDArray[np.float64]:
        peak = peak_level(magnitude)
        dynamic_range_db = self.description.geometry.dynamic_range_db
        decibels = compress(magnitude, peak=peak, dynamic_range_db=dynamic_range_db)
        with torch.no_grad():
            predicted = self.model(torch.from_numpy(decibels).unsqueeze(0).to(self.device))
        return expand(predicted[0].cpu().numpy(), peak=peak, dynamic_range_db=dynamic_range_db)


def same_analysis(first: LogFrequencyGeometry, second: LogFrequencyGeometry) -> bool:
    """Whether two geometries produce the same least-squares reading of one sound.

    The anchor moves the picture along the band axis and the restore moves it back by the same
    whole number of bands, so a restorer taught on either anchor reads the other's magnitude.
    """
    return first.model_copy(update={"anchor": second.anchor}) == second


def restorer_path(library_root: Path, *, name: str = DEFAULT_RESTORER_NAME) -> Path:
    """Where a fitted restorer is written, under the configured library root rather than the repo."""
    return library_root / "models" / f"{name}{RESTORER_SUFFIX}"


def save_restorer(path: Path, model: Restorer, description: RestorerDescription) -> None:
    """Write the weights beside the description that says how to rebuild the network around them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"description": description.model_dump_json(), "state": model.state_dict()}, path)


def load_restorer(path: Path, *, device: torch.device) -> RestoredPghiVocoder:
    """Rebuild a fitted restorer and the vocoder that reads through it.

    Raises:
        FileNotFoundError: no restorer is stored at that path.
    """
    if not path.exists():
        raise FileNotFoundError(f"no restorer is stored at {path}")

    stored = torch.load(path, map_location=device, weights_only=True)
    description = RestorerDescription.model_validate_json(str(stored["description"]))
    model = Restorer(
        RestorerShape(
            channels=description.channels, kernel_size=description.kernel_size, dilations=tuple(description.dilations)
        )
    ).to(device)
    model.load_state_dict(stored["state"])
    model.eval()
    return RestoredPghiVocoder(model=model, description=description, device=device)
