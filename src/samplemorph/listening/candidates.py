from __future__ import annotations

import zlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Final

import numpy as np
from sqlalchemy import Connection

from samplecore.equivalence_classes import classes_by_member_hash, compute_equivalence_classes
from samplecore.models.sample import Sample
from samplecore.models.sample_category import SampleTopCategory
from samplecore.storage.database import chunks
from samplecore.storage.playback_rates import resolved_playback_rates
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_category import PostgresSampleCategoryRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.listening.kinds import SoundKind

TOP_SCORE_SHARE: Final[float] = 0.25
CANDIDATE_BATCH_SIZE: Final[int] = 32
MAXIMUM_POOL_SIZE: Final[int] = 96


@dataclass(frozen=True)
class Candidate:
    """One sample a pair may be drawn from, with everything the draw's guards read of it.

    `rate_hz` is the rate the library plays the sample at, `declared_rates_hz` every distinct rate
    its occurrences and files state, `module_hashes` the modules holding it, and
    `equivalence_class` the group of near-duplicates it belongs to, if any.
    """

    sample: Sample
    label: str
    rate_hz: float
    declared_rates_hz: tuple[float, ...]
    module_hashes: frozenset[str]
    equivalence_class: str | None

    @property
    def sample_hash(self) -> str:
        return self.sample.hash

    @property
    def seconds(self) -> float:
        return self.sample.frames / self.rate_hz

    def is_related_to(self, other: Candidate) -> bool:
        """Whether two candidates share a sample, a module or a group of near-duplicates."""
        same_class = self.equivalence_class is not None and self.equivalence_class == other.equivalence_class
        return self.sample_hash == other.sample_hash or bool(self.module_hashes & other.module_hashes) or same_class


class NoScoringShown(ValueError):
    """Raised when a draw reads categories and the catalog shows no scoring to read them from."""


class CatalogCandidates:
    """The samples each kind of sound offers a draw, read from the catalog a batch at a time.

    A kind's samples are those whose hand label names it and, among the samples a person left
    unlabeled, those the scoring on show hears as that kind first with a score in the top
    `TOP_SCORE_SHARE` of that label's. Hand-labeled samples come first; each tier is shuffled by a
    generator seeded from the draw's seed and the kind's name, so a kind offers the same samples in
    the same order whichever kinds were asked for before it. A kind offers up to `MAXIMUM_POOL_SIZE`
    samples whose audio can be read now and whose playback rate is known.
    """

    def __init__(self, connection: Connection, audio: SampleAudio, *, random_seed: int) -> None:
        categories = PostgresSampleCategoryRepository(connection)
        experiment_id = categories.shown_experiment_id()
        if experiment_id is None:
            raise NoScoringShown("the catalog shows no label scoring, so there are no categories to draw by")

        self.experiment_id = experiment_id
        self._connection = connection
        self._audio = audio
        self._random_seed = random_seed
        self._top_categories = _top_categories(categories.top_categories(experiment_id))
        self._hand_labels = PostgresSampleAnnotationRepository(connection).cataloged_labels()
        self._classes = classes_by_member_hash(
            compute_equivalence_classes(PostgresSampleRelationRepository(connection).list_all())
        )
        self._pools: dict[str, tuple[Candidate, ...]] = {}

    def pool(self, kind: SoundKind) -> tuple[Candidate, ...]:
        if kind.name not in self._pools:
            self._pools[kind.name] = self._read_pool(kind)
        return self._pools[kind.name]

    def _read_pool(self, kind: SoundKind) -> tuple[Candidate, ...]:
        labels = self._labels_of(kind)
        generator = np.random.default_rng([self._random_seed, zlib.crc32(kind.name.encode())])
        hand_tier = sorted(sample_hash for sample_hash in labels if sample_hash in self._hand_labels)
        pick_tier = sorted(sample_hash for sample_hash in labels if sample_hash not in self._hand_labels)
        ordered = [*generator.permutation(hand_tier).tolist(), *generator.permutation(pick_tier).tolist()]
        pool: list[Candidate] = []
        for batch in chunks(ordered, CANDIDATE_BATCH_SIZE):
            pool.extend(self._resolve(tuple(batch), labels=labels))
            if len(pool) >= MAXIMUM_POOL_SIZE:
                break
        return tuple(pool[:MAXIMUM_POOL_SIZE])

    def _labels_of(self, kind: SoundKind) -> dict[str, str]:
        """Every sample of the kind, by hash, with the label it was found under."""
        labels = {sample_hash: label for sample_hash, label in self._hand_labels.items() if kind.is_named_by(label)}
        scored_labels = {label for label in {item.label for item in self._top_categories} if kind.is_named_by(label)}
        for item in self._top_categories:
            if item.sample_hash not in self._hand_labels and item.label in scored_labels:
                labels[item.sample_hash] = item.label
        return labels

    def _resolve(self, hashes: tuple[str, ...], *, labels: dict[str, str]) -> list[Candidate]:
        samples = PostgresSampleRepository(self._connection).get_many(list(hashes))
        rates = resolved_playback_rates(self._connection, list(hashes))
        declared = PostgresSampleRepository(self._connection).rates_by_hash(list(hashes))
        modules: dict[str, set[str]] = defaultdict(set)
        for properties in PostgresSamplePropertiesRepository(self._connection).list_for_samples(hashes):
            modules[properties.sample_hash].add(properties.occurrence.module_hash)
        candidates = []
        for sample_hash in hashes:
            rate = rates.get(sample_hash)
            sample = samples.get(sample_hash)
            if sample is None or rate is None or not self._audio.is_available(sample_hash):
                continue
            equivalence_class = self._classes.get(sample_hash)
            candidates.append(
                Candidate(
                    sample=sample,
                    label=labels[sample_hash],
                    rate_hz=float(rate),
                    declared_rates_hz=tuple(
                        sorted({float(declared_rate) for declared_rate in declared.get(sample_hash, ())})
                    ),
                    module_hashes=frozenset(modules[sample_hash]),
                    equivalence_class=equivalence_class.class_hash if equivalence_class is not None else None,
                )
            )
        return candidates


def _top_categories(categories: tuple[SampleTopCategory, ...]) -> tuple[SampleTopCategory, ...]:
    """Each label's categories whose score lies in the top `TOP_SCORE_SHARE` of that label's scores."""
    by_label: dict[str, list[SampleTopCategory]] = defaultdict(list)
    for category in categories:
        by_label[category.label].append(category)
    top: list[SampleTopCategory] = []
    for label_categories in by_label.values():
        ranked = sorted(label_categories, key=lambda category: (-category.score, category.sample_hash))
        top.extend(ranked[: max(int(np.ceil(len(ranked) * TOP_SCORE_SHARE)), 1)])
    return tuple(top)
