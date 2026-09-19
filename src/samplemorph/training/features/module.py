from __future__ import annotations

from typing import Any, Final

from lightning.pytorch import LightningModule
from lightning.pytorch.core.optimizer import LightningOptimizer
from lightning.pytorch.utilities.types import OptimizerLRSchedulerConfig
from torch import Tensor
from torch.nn import functional
from torch.optim.lr_scheduler import LRScheduler

from samplemorph.features.autoencoder import FeatureAutoencoder
from samplemorph.features.critic import InterpolationCritic
from samplemorph.features.shape import FeatureShape
from samplemorph.training.codec_losses import reconstruction_error
from samplemorph.training.features.losses import (
    adversarial_term,
    critic_error,
    critic_loss,
    drawn_shares,
    interpolated,
    realistic_mix,
    spread_shares,
)
from samplemorph.training.features.settings import FeatureTrainingSettings
from samplemorph.training.metrics import (
    FEATURE_TRAINING_ADVERSARIAL,
    FEATURE_TRAINING_CRITIC,
    FEATURE_TRAINING_LOSS,
    FEATURE_TRAINING_RECONSTRUCTION,
    FEATURE_VALIDATION_ADVERSARIAL,
    FEATURE_VALIDATION_CRITIC_ERROR,
    FEATURE_VALIDATION_RECONSTRUCTION,
    FEATURE_VALIDATION_RECONSTRUCTION_DB,
)
from samplemorph.training.optimizers import scheduled_over_the_run
from samplemorph.training.refusals import ResumeRefused
from samplemorph.training.run_settings import GRADIENT_CLIP

OBJECTIVE_STATE: Final[str] = "feature_objective"
CRITIC_WEIGHT_KEY: Final[str] = "critic_weight"
CRITIC_MIX_KEY: Final[str] = "critic_mix"
GRADIENT_CLIP_ALGORITHM: Final[str] = "norm"


# pylint: disable=arguments-differ
# The trainer declares its hooks as (*args, **kwargs); naming what each one really takes is what
# makes a step readable, so the narrower signatures are deliberate.
class FeatureTrainingModule(LightningModule):
    """Teaches a `FeatureAutoencoder` to reconstruct pooled grids and, by `critic_weight`, to decode its latent lines as sounds.

    Every batch takes two steps, the autoencoder's and then the critic's, each through its own
    optimizer, clipped by `GRADIENT_CLIP` and followed by its own schedule. The autoencoder steps
    with the critic held still, its interpolants read by the critic as it stood; the critic then
    learns from those interpolants and from sounds mixed into their reconstructions. The critic
    learns whatever the weight, so every run measures how plainly its interpolants show.

    The weight and the mix travel in the resume point, and a run resumed under others is refused:
    a change halfway would leave the model the answer to neither question.
    """

    def __init__(self, shape: FeatureShape, *, settings: FeatureTrainingSettings, dynamic_range_db: float) -> None:
        super().__init__()
        self.automatic_optimization = False
        self.autoencoder = FeatureAutoencoder(shape)
        self.critic = InterpolationCritic(shape)
        self._learning_rate = settings.run.learning_rate
        self._critic_weight = settings.critic_weight
        self._critic_mix = settings.critic_mix
        self._dynamic_range_db = dynamic_range_db

    def forward(self, grids: Tensor) -> Tensor:
        reconstructions: Tensor = self.autoencoder(grids)
        return reconstructions

    def training_step(self, grids: Tensor, _batch_index: int) -> None:
        autoencoder_optimizer, critic_optimizer = self._optimizers()
        shares = drawn_shares(grids.shape[0], device=grids.device)
        with self.toggled_optimizer(autoencoder_optimizer):
            latents = self.autoencoder.encoder(grids)
            reconstructions = self.autoencoder.decoder(latents)
            interpolants = self.autoencoder.decoder(interpolated(latents, shares))
            reconstruction = reconstruction_error(reconstructions, grids)
            loss = reconstruction
            if self._critic_weight > 0.0:
                loss = loss + self._critic_weight * adversarial_term(self.critic(interpolants))
            self._stepped(autoencoder_optimizer, loss)
        with self.toggled_optimizer(critic_optimizer):
            interpolant_scores = self.critic(interpolants.detach())
            realistic_scores = self.critic(realistic_mix(grids, reconstructions.detach(), mix=self._critic_mix))
            critic = critic_loss(interpolant_scores, shares, realistic_scores=realistic_scores)
            self._stepped(critic_optimizer, critic)
        for schedule in self._schedules():
            schedule.step()
        self.log(FEATURE_TRAINING_LOSS, loss.detach(), on_step=True, on_epoch=True, prog_bar=True)
        self.log(FEATURE_TRAINING_RECONSTRUCTION, reconstruction.detach(), on_step=False, on_epoch=True)
        self.log(
            FEATURE_TRAINING_ADVERSARIAL, adversarial_term(interpolant_scores.detach()), on_step=False, on_epoch=True
        )
        self.log(FEATURE_TRAINING_CRITIC, critic.detach(), on_step=False, on_epoch=True, prog_bar=True)

    def validation_step(self, grids: Tensor, _batch_index: int) -> None:
        """The reconstruction of the held-out sounds, and what the critic reads of their interpolants at spread shares."""
        latents = self.autoencoder.encoder(grids)
        reconstructions = self.autoencoder.decoder(latents)
        shares = spread_shares(grids.shape[0], device=grids.device)
        interpolant_scores = self.critic(self.autoencoder.decoder(interpolated(latents, shares)))
        batch_size = grids.shape[0]
        self.log(
            FEATURE_VALIDATION_RECONSTRUCTION,
            reconstruction_error(reconstructions, grids),
            prog_bar=True,
            batch_size=batch_size,
        )
        self.log(
            FEATURE_VALIDATION_RECONSTRUCTION_DB,
            self._dynamic_range_db * functional.l1_loss(reconstructions, grids),
            batch_size=batch_size,
        )
        self.log(FEATURE_VALIDATION_ADVERSARIAL, adversarial_term(interpolant_scores), batch_size=batch_size)
        self.log(FEATURE_VALIDATION_CRITIC_ERROR, critic_error(interpolant_scores, shares), batch_size=batch_size)

    def configure_optimizers(self) -> tuple[OptimizerLRSchedulerConfig, OptimizerLRSchedulerConfig]:
        """The autoencoder's optimizer first and the critic's second, each on a schedule over the whole run."""
        return (
            scheduled_over_the_run(self, self.autoencoder.parameters(), learning_rate=self._learning_rate),
            scheduled_over_the_run(self, self.critic.parameters(), learning_rate=self._learning_rate),
        )

    def on_save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        checkpoint[OBJECTIVE_STATE] = {CRITIC_WEIGHT_KEY: self._critic_weight, CRITIC_MIX_KEY: self._critic_mix}

    def on_load_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Refuse a resume point taught under another objective.

        Raises:
            ResumeRefused: the resume point was taught under another critic weight or mix, or records none.
        """
        asked = {CRITIC_WEIGHT_KEY: self._critic_weight, CRITIC_MIX_KEY: self._critic_mix}
        stored = checkpoint.get(OBJECTIVE_STATE)
        if stored != asked:
            raise ResumeRefused(f"the run stopped under {stored} and was asked to continue under {asked}")

    def _stepped(self, optimizer: LightningOptimizer, loss: Tensor) -> None:
        optimizer.zero_grad()
        self.manual_backward(loss)
        self.clip_gradients(
            optimizer.optimizer, gradient_clip_val=GRADIENT_CLIP, gradient_clip_algorithm=GRADIENT_CLIP_ALGORITHM
        )
        optimizer.step()

    def _optimizers(self) -> tuple[LightningOptimizer, LightningOptimizer]:
        """The autoencoder's optimizer and the critic's, in the order `configure_optimizers` gives them.

        Raises:
            TypeError: the trainer holds other than the two optimizers this module configures.
        """
        match self.optimizers():
            case [LightningOptimizer() as autoencoder, LightningOptimizer() as critic]:
                return autoencoder, critic
            case other:
                raise TypeError(f"a feature module steps two optimizers, and the trainer holds {other}")

    def _schedules(self) -> tuple[LRScheduler, LRScheduler]:
        """The autoencoder's schedule and the critic's, stepped once a batch.

        Raises:
            TypeError: the trainer holds other than the two schedules this module configures.
        """
        match self.lr_schedulers():
            case [LRScheduler() as autoencoder, LRScheduler() as critic]:
                return autoencoder, critic
            case other:
                raise TypeError(f"a feature module steps two schedules, and the trainer holds {other}")
