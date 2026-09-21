from __future__ import annotations


class TrainingRefused(ValueError):
    """Raised when a training run cannot go ahead the way its command asked."""


class ResumeRefused(TrainingRefused):
    """Raised when a run asked to continue has nothing to continue from, or would continue on changed inputs."""


class TrainingDataShortfall(TrainingRefused):
    """Raised when a corpus holds too few samples to fill the batches or the validation a run needs."""
