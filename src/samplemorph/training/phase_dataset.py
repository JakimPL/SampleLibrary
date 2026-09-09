from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import librosa
import numpy as np
import torch
from numpy.typing import NDArray
from threadpoolctl import threadpool_limits
from torch.utils.data import Dataset

from samplecore.models.sample import Sample
from samplecore.storage import audio_store
from samplemorph.canonicalizers import Canonicalizer
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.canonicalizers.linear_axis import onto_linear_axis
from samplemorph.geometry import Geometry

DEFAULT_CROP_FRAMES: Final[int] = 128
SILENT_LEVEL: Final[float] = 1e-8

PhaseBatchItem = tuple[NDArray[np.float32], NDArray[np.float32], NDArray[np.float32], int]


@dataclass(frozen=True)
class PhaseExample:
    """One magnitude a vocoder will meet, beside the phase that magnitude belongs with.

    `magnitude` is what the pipeline hands a vocoder: a sample carried through the canonical grid
    and read back onto the linear Fourier axis, smoothed by everything that grid discards.
    `cosine` and `sine` carry the source's own phase over the same frames, which is the phase that
    turns this very magnitude into the reconstruction listening already accepted.
    """

    magnitude: NDArray[np.float32]
    cosine: NDArray[np.float32]
    sine: NDArray[np.float32]
    frame_offset: int = 0


def phase_example(
    waveform: NDArray[np.float64], *, canonicalizer: Canonicalizer, geometry: Geometry
) -> PhaseExample | None:
    """Carry one waveform through the pipeline and pair the result with the phase it came from.

    Both sides are read from the same prepared waveform on the same analysis window, so a frame of
    the magnitude and a frame of the phase describe the same moment and a crop of one matches a crop
    of the other. Preparing it here rather than leaving each side to do its own is what keeps them
    the same waveform: a canonicalizer centers what it is given, and a phase read from an uncentered
    reading would belong to a slightly different signal. A silent waveform returns nothing, since it
    carries no phase to learn.
    """
    mono = prepare_mono(waveform)
    if float(np.abs(mono).max()) < SILENT_LEVEL:
        return None

    spectrogram = canonicalizer.restore(canonicalizer.canonicalize(mono))
    magnitude = onto_linear_axis(spectrogram.magnitude, geometry=geometry)
    truth = librosa.stft(mono, n_fft=geometry.fft_length, hop_length=geometry.hop_length)
    frames = min(magnitude.shape[1], truth.shape[1])
    if frames < 1:
        return None

    angle = np.angle(truth[:, :frames])
    return PhaseExample(
        magnitude=magnitude[:, :frames].astype(np.float32),
        cosine=np.cos(angle).astype(np.float32),
        sine=np.sin(angle).astype(np.float32),
    )


def crop_to(example: PhaseExample, *, crop_frames: int, generator: np.random.Generator) -> PhaseExample:
    """Take a fixed span of frames, so examples of any length stack into one batch.

    A span shorter than the crop rests against silence for the rest of it. The loss counts each
    frame by how loud it is, so those frames carry no weight and teach the model nothing -- whereas
    repeating the sample to fill the crop would join its end to its beginning and teach a phase
    jump that no recording contains.

    The crop remembers where it started, since a phase read from partway through a recording is the
    phase from its beginning turned by that much.
    """
    frames = example.magnitude.shape[1]
    if frames >= crop_frames:
        start = int(generator.integers(0, frames - crop_frames + 1))
        window = slice(start, start + crop_frames)
        return PhaseExample(
            magnitude=example.magnitude[:, window],
            cosine=example.cosine[:, window],
            sine=example.sine[:, window],
            frame_offset=start,
        )

    padding = ((0, 0), (0, crop_frames - frames))
    return PhaseExample(
        magnitude=np.pad(example.magnitude, padding),
        cosine=np.pad(example.cosine, padding, constant_values=1.0),
        sine=np.pad(example.sine, padding),
        frame_offset=0,
    )


class PhaseTrainingSet(Dataset[PhaseBatchItem]):
    """Pairs of pipeline magnitude and source phase, derived from the catalog as they are asked for.

    Deriving each example costs about as long as reading it from a store would, and a whole
    catalog's worth of magnitudes runs to tens of gigabytes, so the pipeline runs in the loader's
    own worker processes instead. That also keeps the training set exactly current with the
    canonicalizer: a change to the grid changes what this yields, with nothing stale to invalidate.

    Which span of a sample gets taken follows the loader's own seed for the epoch, so a long run
    sees many crops of each sample rather than the same one over and over. Setting torch's seed
    before a run fixes the whole sequence, which keeps two runs of one configuration alike.
    """

    def __init__(
        self,
        samples: tuple[Sample, ...],
        *,
        library_root: Path,
        canonicalizer: Canonicalizer,
        crop_frames: int = DEFAULT_CROP_FRAMES,
        random_seed: int,
    ) -> None:
        self._samples = samples
        self._library_root = library_root
        self._canonicalizer = canonicalizer
        self._crop_frames = crop_frames
        self._random_seed = random_seed

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, index: int) -> PhaseBatchItem:
        generator = np.random.default_rng(self._random_seed + index + torch.initial_seed())
        for offset in range(len(self._samples)):
            position = (index + offset) % len(self._samples)
            example = phase_example(
                audio_store.read(self._library_root, self._samples[position]).pcm,
                canonicalizer=self._canonicalizer,
                geometry=self._canonicalizer.geometry,
            )
            if example is not None:
                cropped = crop_to(example, crop_frames=self._crop_frames, generator=generator)
                return cropped.magnitude, cropped.cosine, cropped.sine, cropped.frame_offset

        raise ValueError("every sample in this training set is silent, so no phase can be learned from it")


def limit_worker_threads(_worker_id: int) -> None:
    """Hold each loader process to one compute thread.

    A loader calls this in each worker it starts, handing it that worker's index, which this has no
    use for. Every worker derives its examples through the same linear algebra, and each library
    underneath would otherwise spread one worker's work across every core the machine has. A dozen workers
    doing that at once spend most of their time contending rather than computing: measured here,
    one example costs 96 ms with one thread and the pool as a whole managed 31 examples a second
    across twelve workers, where one thread each reaches four times that.
    """
    threadpool_limits(limits=1)
    torch.set_num_threads(1)
