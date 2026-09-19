from __future__ import annotations

import numpy as np

from samplemorph.training.features.data import ViewBatchSampler


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
