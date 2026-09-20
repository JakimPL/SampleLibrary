from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Generic, Protocol, TypeVar

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.equivalence_classes import EquivalenceClass, classes_by_member_hash, compute_equivalence_classes
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplemorph.training.refusals import TrainingDataShortfall
from samplemorph.training.run_settings import RunSettings

DEFAULT_VALIDATION_SHARE: Final[float] = 0.05


@dataclass(frozen=True)
class ClassSplit:
    """Positions in a cache's sample order: the samples a model is taught on and the ones it is judged on."""

    training_positions: NDArray[np.intp]
    validation_positions: NDArray[np.intp]


def catalog_classes(connection: Connection) -> dict[str, EquivalenceClass]:
    """The catalog's equivalence classes, indexed by every member's hash."""
    return classes_by_member_hash(compute_equivalence_classes(PostgresSampleRelationRepository(connection).list_all()))


def split_by_class(
    hashes: tuple[str, ...], *, classes: Mapping[str, EquivalenceClass], share: float, random_seed: int
) -> ClassSplit:
    """The samples split by whole equivalence classes under the run's seed.

    Every model trained on the library draws its split here, so models taught under one seed and
    share are judged on the same held-out samples.

    Raises:
        TrainingDataShortfall: the split leaves nothing to train on or nothing to validate on.
    """
    held_out = held_out_by_class(hashes, classes=classes, share=share, random_seed=random_seed)
    if held_out.all() or not held_out.any():
        raise TrainingDataShortfall(
            f"holding out {share:.0%} of {len(hashes)} cached samples by class leaves one side empty; "
            "cache more samples or change the validation share"
        )
    return ClassSplit(training_positions=np.flatnonzero(~held_out), validation_positions=np.flatnonzero(held_out))


def held_out_by_class(
    hashes: tuple[str, ...], *, classes: Mapping[str, EquivalenceClass], share: float, random_seed: int
) -> NDArray[np.bool_]:
    """Which samples are held out: whole equivalence classes, drawn in the seed's order until `share` of the samples.

    A tracker module's copies of one sample share a class, so a copy of a validation sound never
    reaches training. A sample outside every class is a class of its own.
    """
    keys = np.asarray(
        [classes[sample_hash].class_hash if sample_hash in classes else sample_hash for sample_hash in hashes]
    )
    distinct, members = np.unique(keys, return_inverse=True)
    order = np.random.default_rng(random_seed).permutation(len(distinct))
    sizes = np.bincount(members, minlength=len(distinct))[order]
    chosen = order[: int(np.searchsorted(np.cumsum(sizes), share * len(hashes))) + 1]
    held_out: NDArray[np.bool_] = np.isin(members, chosen)
    return held_out


class CachedSamples(Protocol):
    """A cache of samples a model is taught over: where it sits, and which samples it holds, in order."""

    @property
    def directory(self) -> Path: ...

    @property
    def hashes(self) -> tuple[str, ...]: ...


Cache = TypeVar("Cache", bound=CachedSamples)


@dataclass(frozen=True)
class CachedCorpus(Generic[Cache]):
    """A cache split into the samples a model is taught on and the ones it is judged on, beside the library they came from."""

    cache: Cache
    library_root: Path
    training_positions: NDArray[np.intp]
    validation_positions: NDArray[np.intp]

    @property
    def validation_hashes(self) -> tuple[str, ...]:
        return tuple(self.cache.hashes[int(position)] for position in self.validation_positions)


class SplitSettings(Protocol):
    """What a trainer's settings tell a split: the share to hold out, and the run whose seed draws it."""

    @property
    def validation_share(self) -> float: ...

    @property
    def run(self) -> RunSettings: ...


def split_corpus(
    connection: Connection, *, cache: Cache, library_root: Path, settings: SplitSettings
) -> CachedCorpus[Cache]:
    """A cache split by the catalog's equivalence classes under a run's seed.

    Raises:
        TrainingDataShortfall: the split leaves nothing to train on or nothing to validate on.
    """
    split = split_by_class(
        cache.hashes,
        classes=catalog_classes(connection),
        share=settings.validation_share,
        random_seed=settings.run.random_seed,
    )
    return CachedCorpus(
        cache=cache,
        library_root=library_root,
        training_positions=split.training_positions,
        validation_positions=split.validation_positions,
    )
