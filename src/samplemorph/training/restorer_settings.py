from __future__ import annotations

from typing import Final

from samplemorph.training.run_settings import TrainingPrecision

# The run that taught the stored restorer over the whole catalog. A 32-crop batch in whole precision
# spends about 19 GiB in activations at 1,025 bins; eight crops in bf16 train on a 12 GiB card.
DEFAULT_RESTORER_EPOCHS: Final[int] = 4
DEFAULT_RESTORER_BATCH_SIZE: Final[int] = 8
DEFAULT_RESTORER_LEARNING_RATE: Final[float] = 1e-3
DEFAULT_RESTORER_PRECISION: Final[TrainingPrecision] = "bf16-mixed"
