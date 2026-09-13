from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import KNeighborsRegressor

from samplecloud.evaluation.corpus import EvaluationCorpus
from samplecloud.evaluation.settings import EvaluationSettings

WELL_STRUCK_THRESHOLD: Final[int] = 8


@dataclass(frozen=True)
class NoteTargetScore:
    """How closely a descriptor's neighbors agree with one target read off the note events."""

    target: str
    spearman: float
    scored_sample_count: int


@dataclass(frozen=True)
class NoteAgreement:
    """Whether a descriptor puts samples the library plays the same way near one another.

    Note events reach almost the whole catalog, which makes this the broadest signal available
    without hand labels. Pitch count and span are continuous targets because the percussive and
    tonal split they were once read as is a tendency rather than a division: percussive categories
    run about half single-pitch against tonal categories' fifth, so a threshold would score a
    descriptor on where the threshold sits.

    `well_struck` repeats the same targets over samples struck at least `WELL_STRUCK_THRESHOLD`
    times. Pitch count is bounded above by strike count -- a sample struck twice shows at most two
    pitches whatever it is -- so a score over every sample partly measures how often each was used.

    `single_pitch_auc` is secondary and carries that same censoring, kept because a reader who wants
    one number for "is this used as a fixed sound" will otherwise invent a worse one.
    """

    targets: tuple[NoteTargetScore, ...]
    well_struck_targets: tuple[NoteTargetScore, ...]
    single_pitch_auc: float
    coverage: float
    scored_sample_count: int
    well_struck_sample_count: int
    neighbor_count: int
    fold_count: int


def note_agreement(corpus: EvaluationCorpus, *, settings: EvaluationSettings) -> NoteAgreement:
    """Predict each sample's pitch count and span from its neighbors, and rank the agreement.

    Raises:
        ValueError: the note events reach too few of this experiment's samples to fold.
    """
    reached = np.flatnonzero(corpus.note_reached)
    if len(reached) < settings.fold_count:
        raise ValueError(f"note events reach {len(reached)} of this experiment's samples, too few to score")

    statistics = [corpus.note_statistics[position] for position in reached]
    pitch_counts = np.array([entry.distinct_pitch_count for entry in statistics if entry is not None], dtype=np.float64)
    spans = np.array([entry.pitch_span_semitones for entry in statistics if entry is not None], dtype=np.float64)
    strikes = np.array([entry.strike_count for entry in statistics if entry is not None], dtype=np.float64)
    vectors = corpus.vectors[reached]
    groups = corpus.equivalence_groups[reached]

    targets = {"log2_pitch_count": np.log2(pitch_counts), "log2_span": np.log2(spans + 1.0)}
    predictions = {name: _predicted(vectors, values, groups, settings=settings) for name, values in targets.items()}
    well_struck = strikes >= WELL_STRUCK_THRESHOLD
    return NoteAgreement(
        targets=tuple(
            NoteTargetScore(target=name, spearman=_spearman(targets[name], predicted), scored_sample_count=len(reached))
            for name, predicted in predictions.items()
        ),
        well_struck_targets=tuple(
            NoteTargetScore(
                target=name,
                spearman=_spearman(targets[name][well_struck], predicted[well_struck]),
                scored_sample_count=int(well_struck.sum()),
            )
            for name, predicted in predictions.items()
        ),
        single_pitch_auc=_single_pitch_auc(pitch_counts, predictions["log2_pitch_count"]),
        coverage=len(reached) / corpus.sample_count,
        scored_sample_count=len(reached),
        well_struck_sample_count=int(well_struck.sum()),
        neighbor_count=settings.neighbor_count,
        fold_count=settings.fold_count,
    )


def _predicted(
    vectors: NDArray[np.float64],
    values: NDArray[np.float64],
    groups: NDArray[np.int64],
    *,
    settings: EvaluationSettings,
) -> NDArray[np.float64]:
    """Each sample's target as its neighbors in the other folds predict it."""
    predictions = np.empty_like(values)
    splitter = GroupKFold(n_splits=settings.fold_count, shuffle=True, random_state=settings.random_seed)
    for train_positions, test_positions in splitter.split(vectors, values, groups=groups):
        regressor = KNeighborsRegressor(n_neighbors=min(settings.neighbor_count, len(train_positions)))
        regressor.fit(vectors[train_positions], values[train_positions])
        predictions[test_positions] = regressor.predict(vectors[test_positions])
    return predictions


def _spearman(observed: NDArray[np.float64], predicted: NDArray[np.float64]) -> float:
    """Rank correlation between a target and its prediction, reading a constant target as no agreement."""
    if observed.size < 2 or np.ptp(observed) == 0.0 or np.ptp(predicted) == 0.0:
        return 0.0

    return float(spearmanr(observed, predicted).statistic)


def _single_pitch_auc(pitch_counts: NDArray[np.float64], predicted: NDArray[np.float64]) -> float:
    """How well the predicted pitch count separates samples played at one pitch from the rest."""
    is_single = pitch_counts <= 1.0
    if is_single.all() or not is_single.any():
        return 0.5

    return float(roc_auc_score(is_single, -predicted))
