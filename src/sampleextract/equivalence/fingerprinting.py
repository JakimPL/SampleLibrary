from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import batched
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection

from samplecore.models.channels import ChannelLayout
from samplecore.models.fingerprint import SampleFingerprint, StoredFingerprint
from samplecore.models.sample import Sample
from samplecore.process_pool import mapped_in_processes
from samplecore.progress import ProgressBar
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.fingerprint import PostgresSampleFingerprintRepository
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplecore.waveform import trim_trailing_silence
from sampleextract.equivalence.candidates import Fingerprints
from sampleextract.equivalence.fingerprint import (
    FINGERPRINT_SIZE,
    FINGERPRINT_VERSION,
    compute_rate_fingerprint,
    compute_shape_fingerprint,
)
from sampleextract.equivalence.scoring import TRAILING_SILENCE_THRESHOLD

FINGERPRINT_CHUNK_SIZE: Final[int] = 64
# Fingerprints are committed this many at a time, so a pass stopped while reading keeps what it read.
FINGERPRINT_COMMIT_ROWS: Final[int] = 1000
FINGERPRINTING_LABEL: Final[str] = "Fingerprinting samples"


@dataclass(frozen=True)
class FingerprintedSamples:
    """What a pass knows of its samples' content: the fingerprint of each sample it can read, and how many it cannot."""

    fingerprints: dict[str, StoredFingerprint]
    unavailable: int

    @property
    def silent(self) -> int:
        return sum(1 for stored in self.fingerprints.values() if stored.fingerprint.silent)


@dataclass(frozen=True)
class _FingerprintReader:
    """Reads a sample and fingerprints its content trimmed of trailing silence, sent once to every worker process.

    Trimming here, as the waveforms the scoring reads are trimmed, makes the fingerprints the
    candidates come from describe the content every detector compares. A sample none of whose files
    holds it now reads as ``None``.
    """

    audio: SampleAudio

    def __call__(self, sample: Sample) -> SampleFingerprint | None:
        try:
            pcm = self.audio.read(sample).pcm
        except SampleUnavailableError:
            return None
        waveform = trim_trailing_silence(pcm, threshold=TRAILING_SILENCE_THRESHOLD)
        if waveform.shape[0] == 0:
            return SampleFingerprint(sample_hash=sample.hash, trimmed_frames=0, shape=None, rate=None)
        return SampleFingerprint(
            sample_hash=sample.hash,
            trimmed_frames=waveform.shape[0],
            shape=compute_shape_fingerprint(waveform).astype(np.float32),
            rate=compute_rate_fingerprint(waveform).astype(np.float32),
        )


def fingerprint_samples(
    connection: Connection, samples: tuple[Sample, ...], audio: SampleAudio, *, workers: int
) -> FingerprintedSamples:
    """Every readable sample's fingerprint, reading over ``workers`` processes only the ones the catalog lacks.

    A fingerprint depends on the sample's content alone, which its hash names, so one read under the
    current `FINGERPRINT_VERSION` is kept and read back by every later pass. The fingerprints a pass
    reads are committed as they come, a thousand at a time, so a pass stopped partway keeps them. A
    sample none of whose files holds it now is counted and left out, and its fingerprint, where one
    is kept, waits for its file to return.
    """
    repository = PostgresSampleFingerprintRepository(connection)
    stored = repository.at_version(FINGERPRINT_VERSION)
    readable = [sample for sample in samples if audio.is_available(sample.hash)]
    missing = [sample for sample in readable if sample.hash not in stored]
    fingerprints = {sample.hash: stored[sample.hash] for sample in readable if sample.hash in stored}
    unavailable = len(samples) - len(readable)
    with ProgressBar(total=len(readable), label=FINGERPRINTING_LABEL, resumed=len(readable) - len(missing)) as progress:
        readings = mapped_in_processes(
            _FingerprintReader(audio),
            missing,
            worker_count=workers,
            chunk_size=FINGERPRINT_CHUNK_SIZE,
            progress=progress,
        )
        for batch in batched(readings, FINGERPRINT_COMMIT_ROWS):
            read = [reading for reading in batch if reading is not None]
            unavailable += len(batch) - len(read)
            with start_batch(connection):
                repository.upsert_many(read, version=FINGERPRINT_VERSION)
            fingerprints.update(
                (fingerprint.sample_hash, StoredFingerprint(fingerprint=fingerprint, compared_version=None))
                for fingerprint in read
            )
    return FingerprintedSamples(fingerprints=fingerprints, unavailable=unavailable)


def comparison_layouts(
    samples: tuple[Sample, ...], fingerprinted: FingerprintedSamples, *, comparison_version: int
) -> tuple[Fingerprints, ...]:
    """The samples holding sound, grouped by channel layout, which relations never cross, each group's compared rows first.

    Within a layout the samples compared under `comparison_version` come first and the rest follow,
    each part in hash order, so a pass searches only from the first sample not yet compared.
    """
    layouts: list[Fingerprints] = []
    for layout in ChannelLayout:
        sounding = [
            (sample, fingerprinted.fingerprints[sample.hash])
            for sample in samples
            if sample.channels is layout
            and sample.hash in fingerprinted.fingerprints
            and not fingerprinted.fingerprints[sample.hash].fingerprint.silent
        ]
        compared = [row for row in sounding if row[1].compared_version == comparison_version]
        new = [row for row in sounding if row[1].compared_version != comparison_version]
        if new:
            layouts.append(_stacked([*compared, *new], first_new=len(compared)))
    return tuple(layouts)


def _stacked(rows: Sequence[tuple[Sample, StoredFingerprint]], *, first_new: int) -> Fingerprints:
    fingerprints = [stored.fingerprint for _, stored in rows]
    return Fingerprints(
        samples=tuple(sample for sample, _ in rows),
        shapes=_vectors([fingerprint.shape for fingerprint in fingerprints]),
        rates=_vectors([fingerprint.rate for fingerprint in fingerprints]),
        trimmed_frames=np.array([fingerprint.trimmed_frames for fingerprint in fingerprints], dtype=np.int64),
        first_new=first_new,
    )


def _vectors(vectors: list[NDArray[np.float32] | None]) -> NDArray[np.float32]:
    stacked = np.empty((len(vectors), FINGERPRINT_SIZE), dtype=np.float32)
    for row, vector in enumerate(vectors):
        if vector is None:
            raise ValueError("a silent sample holds no fingerprint to compare")
        stacked[row] = vector
    return stacked
