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

CODEC_TRAINING_LOSS: Final[str] = "training/loss"
CODEC_TRAINING_RECONSTRUCTION: Final[str] = "training/reconstruction"
CODEC_TRAINING_PRIOR: Final[str] = "training/prior"
CODEC_TRAINING_CYCLE: Final[str] = "training/cycle"
CODEC_VALIDATION_LOSS: Final[str] = "validation/loss"
CODEC_VALIDATION_RECONSTRUCTION: Final[str] = "validation/reconstruction"
CODEC_VALIDATION_PRIOR: Final[str] = "validation/prior"
CODEC_VALIDATION_CYCLE: Final[str] = "validation/cycle"

CODEC_MONITORED_METRIC: Final[str] = CODEC_VALIDATION_LOSS

RESTORER_TRAINING_LOSS: Final[str] = "training/loss"
RESTORER_VALIDATION_LOSS: Final[str] = "validation/loss"
RESTORER_VALIDATION_FINE: Final[str] = "validation/fine"
RESTORER_VALIDATION_COARSE: Final[str] = "validation/coarse"
RESTORER_VALIDATION_LEAST_SQUARES: Final[str] = "validation/least_squares"

RESTORER_MONITORED_METRIC: Final[str] = RESTORER_VALIDATION_LOSS

FEATURE_TRAINING_LOSS: Final[str] = "training/loss"
FEATURE_TRAINING_RECONSTRUCTION: Final[str] = "training/reconstruction"
FEATURE_TRAINING_ADVERSARIAL: Final[str] = "training/adversarial"
FEATURE_TRAINING_CRITIC: Final[str] = "training/critic"
FEATURE_VALIDATION_RECONSTRUCTION: Final[str] = "validation/reconstruction"
FEATURE_VALIDATION_RECONSTRUCTION_DB: Final[str] = "validation/reconstruction_db"
FEATURE_VALIDATION_ADVERSARIAL: Final[str] = "validation/adversarial"
FEATURE_VALIDATION_CRITIC_ERROR: Final[str] = "validation/critic_error"

FEATURE_MONITORED_METRIC: Final[str] = FEATURE_VALIDATION_RECONSTRUCTION

PITCH_TRAINING_LOSS: Final[str] = "training/loss"
PITCH_TRAINING_EQUIVARIANCE: Final[str] = "training/equivariance"
PITCH_TRAINING_SHIFT: Final[str] = "training/shift"
PITCH_TRAINING_INVARIANCE: Final[str] = "training/invariance"
PITCH_VALIDATION_ERROR: Final[str] = "validation/error"
PITCH_VALIDATION_RETUNING: Final[str] = "validation/retuning_error"
PITCH_VALIDATION_WITHIN: Final[str] = "validation/retuning_within_share"
PITCH_VALIDATION_INVARIANCE: Final[str] = "validation/invariance_drift"
PITCH_VALIDATION_RELIABILITY: Final[str] = "validation/reliability"

PITCH_MONITORED_METRIC: Final[str] = PITCH_VALIDATION_ERROR
