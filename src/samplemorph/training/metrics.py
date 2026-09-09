from __future__ import annotations

from typing import Final

TRAINING_LOSS: Final[str] = "training/loss"
VALIDATION_LOSS: Final[str] = "validation/loss"
VALIDATION_GRADIENT: Final[str] = "validation/gradient"
VALIDATION_SPECTRAL: Final[str] = "validation/spectral"

MONITORED_METRIC: Final[str] = VALIDATION_LOSS
LOGGED_METRICS: Final[tuple[str, ...]] = (
    TRAINING_LOSS,
    VALIDATION_LOSS,
    VALIDATION_GRADIENT,
    VALIDATION_SPECTRAL,
)
