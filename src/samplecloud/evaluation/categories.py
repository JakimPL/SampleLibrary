from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neighbors import KNeighborsClassifier

from samplecloud.evaluation.corpus import EvaluationCorpus
from samplecloud.evaluation.settings import EvaluationSettings
from samplecore.models.category import SampleCategory

MINIMUM_MEMBERS_PER_CATEGORY: Final[int] = 5


@dataclass(frozen=True)
class CategoryScore:
    """How one category fared, beside how many samples carry it."""

    category: str
    f1: float
    support: int


@dataclass(frozen=True)
class CategoryAgreement:
    """Whether a descriptor puts samples the keyword table calls the same thing near one another.

    `coverage` travels with the result because a keyword matches roughly a tenth of the catalog, so
    this score describes that tenth and any reader has to be told so. `macro_f1` sits beside
    `accuracy` because supports run from around a hundred to a few thousand, and an accuracy is
    decided by the largest categories alone.
    """

    accuracy: float
    macro_f1: float
    coverage: float
    scored_sample_count: int
    neighbor_count: int
    fold_count: int
    per_category: tuple[CategoryScore, ...]


def category_agreement(corpus: EvaluationCorpus, *, settings: EvaluationSettings) -> CategoryAgreement:
    """Classify each keyword-labeled sample from its neighbors, across grouped stratified folds.

    `UNCATEGORIZED` stays out: it records that no keyword matched rather than a class the samples
    share, so scoring it would reward a descriptor for gathering everything the table failed to name.
    Categories too small to appear in every fold stay out as well, since a fold that holds none of a
    class cannot score it.

    Raises:
        ValueError: fewer than two categories carry enough samples to be scored.
    """
    selected = _scorable(corpus, fold_count=settings.fold_count)
    labels = np.array([str(corpus.categories[position]) for position in selected])
    if len(set(labels.tolist())) < 2:
        raise ValueError("fewer than two categories carry enough samples to score a descriptor against")

    vectors = corpus.vectors[selected]
    groups = corpus.equivalence_groups[selected]
    predictions = np.empty_like(labels)
    splitter = StratifiedGroupKFold(n_splits=settings.fold_count, shuffle=True, random_state=settings.random_seed)
    for train_positions, test_positions in splitter.split(vectors, labels, groups=groups):
        classifier = KNeighborsClassifier(n_neighbors=min(settings.neighbor_count, len(train_positions)))
        classifier.fit(vectors[train_positions], labels[train_positions])
        predictions[test_positions] = classifier.predict(vectors[test_positions])

    present = sorted(set(labels.tolist()))
    per_category = tuple(
        CategoryScore(
            category=category,
            f1=float(f1_score(labels == category, predictions == category, zero_division=0.0)),
            support=int((labels == category).sum()),
        )
        for category in present
    )
    return CategoryAgreement(
        accuracy=float((predictions == labels).mean()),
        macro_f1=float(f1_score(labels, predictions, average="macro", labels=present, zero_division=0.0)),
        coverage=len(selected) / corpus.sample_count,
        scored_sample_count=len(selected),
        neighbor_count=settings.neighbor_count,
        fold_count=settings.fold_count,
        per_category=per_category,
    )


def _scorable(corpus: EvaluationCorpus, *, fold_count: int) -> NDArray[np.intp]:
    """Positions of the samples a category score can be read over."""
    counts: dict[SampleCategory, int] = {}
    for category in corpus.categories:
        counts[category] = counts.get(category, 0) + 1
    large_enough = {
        category
        for category, count in counts.items()
        if category is not SampleCategory.UNCATEGORIZED and count >= max(fold_count, MINIMUM_MEMBERS_PER_CATEGORY)
    }
    return np.flatnonzero(np.array([category in large_enough for category in corpus.categories]))
