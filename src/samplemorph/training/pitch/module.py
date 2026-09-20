from __future__ import annotations

from typing import Any, Final

import torch
from lightning.pytorch import LightningModule
from lightning.pytorch.utilities.types import OptimizerLRSchedulerConfig
from torch import Tensor
from torch.nn import functional

from samplemorph.coordinates.pitch_head.network import PitchNetwork
from samplemorph.coordinates.pitch_head.readout import SoundReadout, read_sound
from samplemorph.coordinates.pitch_head.shape import PitchHeadShape
from samplemorph.training.metrics import (
    PITCH_TRAINING_EQUIVARIANCE,
    PITCH_TRAINING_INVARIANCE,
    PITCH_TRAINING_LOSS,
    PITCH_TRAINING_SHIFT,
    PITCH_VALIDATION_ERROR,
    PITCH_VALIDATION_INVARIANCE,
    PITCH_VALIDATION_RELIABILITY,
    PITCH_VALIDATION_RETUNING,
    PITCH_VALIDATION_WITHIN,
)
from samplemorph.training.optimizers import scheduled_over_the_run
from samplemorph.training.pitch.augmentation import FrameAugmentation
from samplemorph.training.pitch.data import HeldOutBatch
from samplemorph.training.pitch.losses import equivariance_loss, invariance_cross_entropy, shift_cross_entropy
from samplemorph.training.pitch.settings import PitchTrainingSettings
from samplemorph.training.refusals import ResumeRefused

OBJECTIVE_STATE: Final[str] = "pitch_objective"
WITHIN_SEMITONES: Final[float] = 0.5


# pylint: disable=arguments-differ
# The trainer declares its hooks as (*args, **kwargs); naming what each one really takes is what
# makes a step readable, so the narrower signatures are deliberate.
class PitchTrainingModule(LightningModule):
    """Teaches a `PitchNetwork` that a crop moved along the bin axis is answered the same distance away.

    Every frame is read as three views: two crops of it, drawn at their own shifts, and a second
    augmentation of the first crop. The two crops price how far the answers stand apart against how
    far the crops do, and bin by bin against each other moved; the two augmentations of one crop
    price everything a pitch is not. No label names a pitch anywhere in the run.

    The weights and the reach travel in the resume point, and a run resumed under others is refused:
    a change halfway would leave the head the answer to neither question.
    """

    def __init__(self, shape: PitchHeadShape, *, settings: PitchTrainingSettings, frame_range_db: float) -> None:
        super().__init__()
        self.network = PitchNetwork(shape)
        self._shape = shape
        self._augment = FrameAugmentation(settings=settings.augmentation, frame_range_db=frame_range_db)
        self._reach_bins = max(int(round(settings.shift_reach_semitones * shape.bins_per_semitone)), 1)
        self._ratio_per_bin = float(2.0 ** (1.0 / shape.bins_per_octave))
        self._weights = (settings.equivariance_weight, settings.shift_weight, settings.invariance_weight)
        self._learning_rate = settings.run.learning_rate

    def forward(self, frames: Tensor) -> Tensor:
        distributions: Tensor = self.network(frames)
        return distributions

    def training_step(self, frames: Tensor, _batch_index: int) -> Tensor:
        padded = functional.pad(frames, (self._reach_bins, self._reach_bins))
        first_shift, second_shift = self._drawn_shifts(frames), self._drawn_shifts(frames)
        first = self.network(self._augment(self._cropped(padded, shifts=first_shift)))
        second = self.network(self._augment(self._cropped(padded, shifts=second_shift)))
        again = self.network(self._augment(self._cropped(padded, shifts=first_shift)))
        shifts = second_shift - first_shift
        equivariance = equivariance_loss(first, second, shift_bins=shifts, ratio_per_bin=self._ratio_per_bin)
        shift = shift_cross_entropy(second, target=first, shift_bins=shifts)
        invariance = invariance_cross_entropy(first, again)
        equivariance_weight, shift_weight, invariance_weight = self._weights
        loss = equivariance_weight * equivariance + shift_weight * shift + invariance_weight * invariance
        self.log(PITCH_TRAINING_LOSS, loss.detach(), on_step=True, on_epoch=True, prog_bar=True)
        self.log(PITCH_TRAINING_EQUIVARIANCE, equivariance.detach(), on_step=False, on_epoch=True)
        self.log(PITCH_TRAINING_SHIFT, shift.detach(), on_step=False, on_epoch=True)
        self.log(PITCH_TRAINING_INVARIANCE, invariance.detach(), on_step=False, on_epoch=True)
        return loss

    def validation_step(self, batch: HeldOutBatch, _batch_index: int) -> None:
        """How far the held-out samples' true retunings read from the retuning itself, and how far augmentation moves them."""
        stored, stored_count, retuned, retuned_count, offsets = batch
        stored_readout = self._read(stored, counts=stored_count, augmented=False)
        moved = self._semitones(self._read(retuned, counts=retuned_count, augmented=False).bins - stored_readout.bins)
        retuning_error = (moved - offsets).abs()
        first_view = self._read(stored, counts=stored_count, augmented=True)
        second_view = self._read(stored, counts=stored_count, augmented=True)
        drift = self._semitones(first_view.bins - second_view.bins).abs()
        batch_size = stored.shape[0]
        self.log(PITCH_VALIDATION_ERROR, retuning_error.mean() + drift.mean(), prog_bar=True, batch_size=batch_size)
        self.log(PITCH_VALIDATION_RETUNING, retuning_error.mean(), prog_bar=True, batch_size=batch_size)
        self.log(
            PITCH_VALIDATION_WITHIN, (retuning_error <= WITHIN_SEMITONES).to(moved.dtype).mean(), batch_size=batch_size
        )
        self.log(PITCH_VALIDATION_INVARIANCE, drift.mean(), batch_size=batch_size)
        self.log(PITCH_VALIDATION_RELIABILITY, stored_readout.reliability.mean(), batch_size=batch_size)

    def configure_optimizers(self) -> OptimizerLRSchedulerConfig:
        return scheduled_over_the_run(self, self.network.parameters(), learning_rate=self._learning_rate)

    def on_save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        checkpoint[OBJECTIVE_STATE] = self._objective()

    def on_load_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Refuse a resume point taught under another objective.

        Raises:
            ResumeRefused: the resume point was taught under other weights or another reach, or records none.
        """
        stored = checkpoint.get(OBJECTIVE_STATE)
        if stored != self._objective():
            raise ResumeRefused(f"the run stopped under {stored} and was asked to continue under {self._objective()}")

    def _objective(self) -> dict[str, float]:
        equivariance_weight, shift_weight, invariance_weight = self._weights
        return {
            "equivariance_weight": equivariance_weight,
            "shift_weight": shift_weight,
            "invariance_weight": invariance_weight,
            "reach_bins": float(self._reach_bins),
        }

    def _drawn_shifts(self, frames: Tensor) -> Tensor:
        return torch.randint(
            -self._reach_bins, self._reach_bins + 1, (frames.shape[0],), device=frames.device, dtype=torch.long
        )

    def _cropped(self, padded: Tensor, *, shifts: Tensor) -> Tensor:
        """The band count's worth of bins holding the frame moved by each item's shift. Shape: ``(batch, bands)``."""
        bins = torch.arange(self._shape.band_count, device=padded.device)
        positions = bins[None, :] + self._reach_bins - shifts[:, None]
        return padded.gather(1, positions)

    def _read(self, readings: Tensor, *, counts: Tensor, augmented: bool) -> SoundReadout:
        """What a batch of samples' readings answer together, every frame read at once."""
        batch, frames, bands = readings.shape
        flattened = readings.reshape(batch * frames, bands)
        distributions = self.network(self._augment(flattened) if augmented else flattened)
        valid = (torch.arange(frames, device=readings.device)[None, :] < counts[:, None]).to(readings.dtype)
        return read_sound(
            distributions.reshape(batch, frames, -1), valid=valid, reach_bins=self._shape.readout_reach_bins
        )

    def _semitones(self, bins: Tensor) -> Tensor:
        return bins / self._shape.bins_per_semitone
