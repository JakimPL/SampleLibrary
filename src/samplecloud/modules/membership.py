from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.spectral_distance import SpectralVectors
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository


@dataclass(frozen=True)
class ModuleSampleSets:
    """Every module's embedded samples, as sets of rows into one matrix of spectral vectors.

    ``vectors`` holds each sample that belongs to at least one module exactly once, in single
    precision, and ``member_rows[index]`` lists the rows of the module named by
    ``module_hashes[index]``. A module appears only when at least one of its samples has a vector.
    """

    module_hashes: tuple[str, ...]
    member_rows: tuple[NDArray[np.intp], ...]
    vectors: NDArray[np.float32]


def load_module_sample_sets(connection: Connection) -> ModuleSampleSets:
    """Read which samples each module holds and pair them with the promoted spectral vectors."""
    members = PostgresSamplePropertiesRepository(connection).sample_hashes_by_module()
    spectral = PostgresSampleSpectralFeatureRepository(connection).vectors()
    return module_sample_sets(members, spectral)


def module_sample_sets(members: Mapping[str, frozenset[str]], spectral: SpectralVectors) -> ModuleSampleSets:
    """Keep each module's samples that carry a spectral vector and gather those vectors into one matrix.

    Modules and their samples are ordered by hash, so the same catalog always yields the same rows.
    """
    embedded_members = _embedded_members(members, spectral)
    used_hashes = sorted({sample_hash for sample_hashes in embedded_members.values() for sample_hash in sample_hashes})
    if not used_hashes:
        return ModuleSampleSets(module_hashes=(), member_rows=(), vectors=np.empty((0, 0), dtype=np.float32))

    compact_row = {sample_hash: row for row, sample_hash in enumerate(used_hashes)}
    source_rows = np.array([spectral.row_by_hash[sample_hash] for sample_hash in used_hashes], dtype=np.intp)
    return ModuleSampleSets(
        module_hashes=tuple(embedded_members),
        member_rows=tuple(
            np.array([compact_row[sample_hash] for sample_hash in sample_hashes], dtype=np.intp)
            for sample_hashes in embedded_members.values()
        ),
        vectors=spectral.matrix[source_rows].astype(np.float32),
    )


def _embedded_members(members: Mapping[str, frozenset[str]], spectral: SpectralVectors) -> dict[str, tuple[str, ...]]:
    embedded_members: dict[str, tuple[str, ...]] = {}
    for module_hash in sorted(members):
        sample_hashes = tuple(sorted(members[module_hash] & spectral.row_by_hash.keys()))
        if sample_hashes:
            embedded_members[module_hash] = sample_hashes
    return embedded_members
