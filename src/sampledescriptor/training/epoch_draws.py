from __future__ import annotations

from collections.abc import Iterator
from typing import Final, TypeVar

import numpy as np
from numpy.typing import NDArray
from torch.utils.data import Sampler

ORDER_STREAM: Final[int] = 0
VIEW_STREAM: Final[int] = 1
SEED_MODULUS: Final[int] = 2**64

# (index into the training set, the seed its crop is drawn from)
# (position in the corpus, which retuned view pairs with its stored grid)
ViewRequest = tuple[int, int]


def epoch_generator(random_seed: int, *, stream: int, epoch: int) -> np.random.Generator:
    """The generator one kind of draw uses in one epoch, the same whichever process or run asks.

    Every draw a trainer makes per epoch is a function of the run's seed, the kind of draw and the
    epoch alone, so loader workers draw nothing themselves and a resumed run replays exactly the
    epoch it resumes at.
    """
    return np.random.default_rng([random_seed % SEED_MODULUS, stream, epoch])


class EpochPermutation(Sampler[int]):
    """Walks a set of items in a fresh order every epoch, fixed by the seed and the epoch.

    The trainer hands the epoch over through `set_epoch` before each pass, on this sampler and on
    the sampler a batch sampler exposes as its own.
    """

    def __init__(self, items: NDArray[np.intp], *, random_seed: int) -> None:
        super().__init__()
        self._items = items
        self._random_seed = random_seed
        self._epoch = 0

    @property
    def epoch(self) -> int:
        return self._epoch

    def set_epoch(self, epoch: int) -> None:
        self._epoch = epoch

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[int]:
        generator = epoch_generator(self._random_seed, stream=ORDER_STREAM, epoch=self._epoch)
        return iter(generator.permutation(self._items).tolist())


Request = TypeVar("Request")
