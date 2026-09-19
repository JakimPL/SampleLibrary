from __future__ import annotations

import numpy as np

from samplecore.equivalence_classes import EquivalenceClass
from samplemorph.training.features.data import ViewBatchSampler, held_out_by_class

SAMPLE_COUNT = 200
SHARE = 0.1
HASHES = tuple(format(position + 1, "064x") for position in range(SAMPLE_COUNT))


def _classes(group_size: int) -> dict[str, EquivalenceClass]:
    """Every run of `group_size` consecutive hashes as one class, the way a tracker's copies of one sample would be."""
    classes: dict[str, EquivalenceClass] = {}
    for start in range(0, SAMPLE_COUNT, group_size):
        members = HASHES[start : start + group_size]
        equivalence_class = EquivalenceClass(class_hash=f"class-{start}", member_hashes=members)
        classes.update({member: equivalence_class for member in members})
    return classes


def test_a_class_is_held_out_whole_or_taught_whole() -> None:
    classes = _classes(group_size=7)

    held_out = held_out_by_class(HASHES, classes=classes, share=SHARE, random_seed=0)

    for start in range(0, SAMPLE_COUNT, 7):
        assert len(set(held_out[start : start + 7].tolist())) == 1


def test_the_held_out_share_is_reached_by_the_last_class_drawn() -> None:
    held_out = held_out_by_class(HASHES, classes=_classes(group_size=7), share=SHARE, random_seed=0)

    assert SHARE * SAMPLE_COUNT <= held_out.sum() < SHARE * SAMPLE_COUNT + 7


def test_a_sample_outside_every_class_is_a_class_of_its_own() -> None:
    held_out = held_out_by_class(HASHES, classes={}, share=SHARE, random_seed=0)

    assert held_out.sum() == round(SHARE * SAMPLE_COUNT)


def test_the_split_follows_the_seed() -> None:
    classes = _classes(group_size=3)

    first = held_out_by_class(HASHES, classes=classes, share=SHARE, random_seed=0)

    assert np.array_equal(first, held_out_by_class(HASHES, classes=classes, share=SHARE, random_seed=0))
    assert not np.array_equal(first, held_out_by_class(HASHES, classes=classes, share=SHARE, random_seed=1))


def test_every_batch_is_whole_and_reads_each_sample_at_one_of_its_views_drawn_afresh_every_epoch() -> None:
    sampler = ViewBatchSampler(np.arange(10, 31), batch_size=4, view_count=3, random_seed=0)

    first = list(sampler)
    sampler.sampler.set_epoch(1)
    second = list(sampler)

    assert len(first) == len(sampler) == 5
    assert all(len(batch) == 4 for batch in first)
    requests = [request for batch in first for request in batch]
    assert len({position for position, _ in requests}) == len(requests)
    assert {position for position, _ in requests} <= set(range(10, 31))
    assert {view for _, view in requests} == {0, 1, 2}
    assert first != second
