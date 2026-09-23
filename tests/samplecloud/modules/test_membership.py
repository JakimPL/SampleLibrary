from __future__ import annotations

import numpy as np

from samplecloud.modules.membership import module_sample_sets
from samplecore.spectral_distance import SpectralVectors

SAMPLE_A = "a" * 64
SAMPLE_B = "b" * 64
SAMPLE_UNEMBEDDED = "c" * 64
MODULE_FIRST = "1" * 64
MODULE_SECOND = "2" * 64
MODULE_UNEMBEDDED = "3" * 64


def _spectral() -> SpectralVectors:
    return SpectralVectors(hashes=(SAMPLE_B, SAMPLE_A), matrix=np.array([[3.0, 4.0], [0.0, 0.0]]))


def test_a_sample_without_a_vector_is_left_out_of_its_module() -> None:
    sets = module_sample_sets({MODULE_FIRST: frozenset({SAMPLE_A, SAMPLE_UNEMBEDDED})}, _spectral())

    assert sets.module_hashes == (MODULE_FIRST,)
    np.testing.assert_array_equal(sets.vectors[sets.member_rows[0]], [[0.0, 0.0]])


def test_a_module_without_any_embedded_sample_is_left_out() -> None:
    sets = module_sample_sets(
        {MODULE_UNEMBEDDED: frozenset({SAMPLE_UNEMBEDDED}), MODULE_FIRST: frozenset({SAMPLE_A})}, _spectral()
    )

    assert sets.module_hashes == (MODULE_FIRST,)


def test_a_sample_shared_by_two_modules_is_held_once() -> None:
    sets = module_sample_sets(
        {MODULE_FIRST: frozenset({SAMPLE_A, SAMPLE_B}), MODULE_SECOND: frozenset({SAMPLE_B})}, _spectral()
    )

    assert sets.vectors.shape == (2, 2)
    assert sets.vectors.dtype == np.float32
    assert set(sets.member_rows[1]) <= set(sets.member_rows[0])


def test_no_modules_give_empty_sets() -> None:
    sets = module_sample_sets({}, _spectral())

    assert sets.module_hashes == ()
    assert sets.member_rows == ()
