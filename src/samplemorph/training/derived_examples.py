from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Protocol, TypeVar

import numpy as np
from numpy.typing import NDArray
from torch.utils.data import Dataset

from samplecore.models.sample import Sample
from samplecore.storage import audio_store
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.geometry import Geometry
from samplemorph.training.epoch_draws import CropRequest

Example = TypeVar("Example")
Example_co = TypeVar("Example_co", covariant=True)
Example_contra = TypeVar("Example_contra", contravariant=True)
Item = TypeVar("Item")
Item_co = TypeVar("Item_co", covariant=True)


class ExampleDeriver(Protocol[Example_co]):
    """Carries one waveform through the pipeline into one family's example, or nothing for silence."""

    def __call__(
        self, waveform: NDArray[np.float64], *, canonicalizer: Canonicalizer, geometry: Geometry
    ) -> Example_co | None: ...


class ExampleCropper(Protocol[Example_contra, Item_co]):
    """Takes one family's fixed span of frames from an example and lays it out as a batch item."""

    def __call__(self, example: Example_contra, *, crop_frames: int, generator: np.random.Generator) -> Item_co: ...


@dataclass(frozen=True)
class ExampleFamily(Generic[Example, Item]):
    """One family's way of turning a catalog sample into a batch item: derive an example, then crop it."""

    derive: ExampleDeriver[Example]
    crop: ExampleCropper[Example, Item]
    crop_frames: int


class DerivedExampleSet(Dataset[Item], Generic[Example, Item]):
    """Examples derived from the catalog's audio as they are asked for, one family's way.

    Deriving each example costs about as long as reading it from a store would, and a whole
    catalog's worth of magnitudes runs to tens of gigabytes, so the pipeline runs in the loader's
    own worker processes instead. That also keeps the training set exactly current with the
    canonicalizer: a change to the grid changes what this yields, with nothing stale to invalidate.

    Each request names a sample and the seed its crop is drawn from, which the loader's sampler
    chooses per epoch, so a long run sees many crops of each sample and two runs of one seed see
    the same ones. A silent sample yields the next sample along instead, so every request answers.
    """

    def __init__(
        self,
        samples: tuple[Sample, ...],
        *,
        library_root: Path,
        canonicalizer: Canonicalizer,
        family: ExampleFamily[Example, Item],
    ) -> None:
        self._samples = samples
        self._library_root = library_root
        self._canonicalizer = canonicalizer
        self._family = family

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, request: CropRequest) -> Item:
        index, crop_seed = request
        generator = np.random.default_rng(crop_seed)
        for offset in range(len(self._samples)):
            position = (index + offset) % len(self._samples)
            example = self._family.derive(
                audio_store.read(self._library_root, self._samples[position]).pcm,
                canonicalizer=self._canonicalizer,
                geometry=self._canonicalizer.geometry,
            )
            if example is not None:
                return self._family.crop(example, crop_frames=self._family.crop_frames, generator=generator)

        raise ValueError("every sample in this training set is silent, so there is nothing to learn from it")
