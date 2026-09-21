from __future__ import annotations

from typing import Final

DESCRIPTOR_TRAINING_LOSS: Final[str] = "training/loss"
DESCRIPTOR_TRAINING_DISTILLATION: Final[str] = "training/distillation"
DESCRIPTOR_TRAINING_RETUNING: Final[str] = "training/retuning"
DESCRIPTOR_TRAINING_LABELS: Final[str] = "training/labels"
DESCRIPTOR_VALIDATION_LOSS: Final[str] = "validation/loss"
DESCRIPTOR_VALIDATION_TEACHER_COSINE: Final[str] = "validation/teacher_cosine"
DESCRIPTOR_VALIDATION_RETUNE_RANK_ONE: Final[str] = "validation/retune_rank_one"
DESCRIPTOR_VALIDATION_NDCG: Final[str] = "validation/hand_label_ndcg"

DESCRIPTOR_MONITORED_METRIC: Final[str] = DESCRIPTOR_VALIDATION_LOSS
