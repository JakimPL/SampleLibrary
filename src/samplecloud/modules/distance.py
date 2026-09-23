from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_array

from samplecloud.modules.membership import ModuleSampleSets

BATCH_MEMBER_COUNT: Final[int] = 512


def chamfer_distances(sets: ModuleSampleSets) -> NDArray[np.float32]:
    """The symmetric Chamfer distance between every pair of modules' sample sets.

    The directed distance from module A to module B is the mean, over A's samples, of each one's
    distance to B's closest sample; the result averages both directions. Averaging over each
    module's own samples keeps modules of different sizes comparable: a module that adds one sample
    to another's set lies that sample's distance divided by twice its own size away.

    Modules are measured in batches of about ``BATCH_MEMBER_COUNT`` member samples: one matrix
    product gives every sample's distance to each batch member, and each batch folds straight into
    the directed distances, so memory grows with the module count squared plus one batch of columns.
    """
    module_count = len(sets.module_hashes)
    squared_norms = np.einsum("ij,ij->i", sets.vectors, sets.vectors)
    averaging = _averaging_matrix(sets)
    # (modules, modules): row A, column B holds the directed distance from A to B.
    directed = np.empty((module_count, module_count), dtype=np.float32)
    for batch in _batches(sets.member_rows):
        nearest = _nearest_distances(sets, batch, squared_norms=squared_norms)
        directed[:, batch.start : batch.stop] = averaging @ nearest
    distances: NDArray[np.float32] = (0.5 * (directed + directed.T)).astype(np.float32)
    return distances


def _batches(member_rows: tuple[NDArray[np.intp], ...]) -> Iterator[range]:
    """Consecutive runs of modules holding about ``BATCH_MEMBER_COUNT`` samples between them."""
    start = 0
    members = 0
    for index, rows in enumerate(member_rows):
        members += len(rows)
        if members >= BATCH_MEMBER_COUNT:
            yield range(start, index + 1)
            start, members = index + 1, 0
    if start < len(member_rows):
        yield range(start, len(member_rows))


def _nearest_distances(
    sets: ModuleSampleSets, batch: range, *, squared_norms: NDArray[np.float32]
) -> NDArray[np.float32]:
    """How far each sample lies from the closest sample of each module in ``batch``.

    A module's own samples lie at exactly 0 from it, so two modules holding the same set of samples
    come out exactly 0 apart once the distances are averaged.
    """
    batch_rows = [sets.member_rows[module] for module in batch]
    columns = np.concatenate(batch_rows)
    offsets = np.cumsum([0, *(len(rows) for rows in batch_rows[:-1])])
    vectors = sets.vectors
    # (samples, batch members): squared distances from every sample to each member of the batch.
    squared = squared_norms[:, None] - 2.0 * (vectors @ vectors[columns].T) + squared_norms[columns][None, :]
    # (samples, batch modules): the closest member of each module, one column per module.
    nearest: NDArray[np.float32] = np.sqrt(np.clip(np.minimum.reduceat(squared, offsets, axis=1), 0.0, None))
    for column, rows in enumerate(batch_rows):
        nearest[rows, column] = 0.0
    return nearest


def _averaging_matrix(sets: ModuleSampleSets) -> csr_array:
    """A sparse (modules, samples) matrix whose product with per-sample values averages them per module."""
    sizes = np.array([len(rows) for rows in sets.member_rows], dtype=np.intp)
    weights = np.repeat(1.0 / sizes, sizes).astype(np.float32)
    module_indices = np.repeat(np.arange(len(sizes)), sizes)
    sample_indices = np.concatenate(sets.member_rows) if sets.member_rows else np.empty(0, dtype=np.intp)
    return csr_array((weights, (module_indices, sample_indices)), shape=(len(sizes), len(sets.vectors)))
