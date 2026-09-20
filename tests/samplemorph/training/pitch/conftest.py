from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from samplemorph.coordinates.frames import frame_analysis
from samplemorph.training.frame_cache import (
    COUNTS_FILE_NAME,
    DESCRIPTION_FILE_NAME,
    FRAMES_FILE_NAME,
    HASHES_FILE_NAME,
    OFFSETS_FILE_NAME,
    READING_COUNT,
    RETUNED_READING,
    STORED_READING,
    FrameCache,
    FrameCacheDescription,
    open_frame_cache,
)

ANALYSIS = frame_analysis()
CACHED_SAMPLE_COUNT = 24
RETUNING_RANGE_SEMITONES = 7.0
LOWEST_FUNDAMENTAL_BIN = 60
FUNDAMENTAL_STEP_BINS = 6
HARMONIC_COUNT = 8
COMB_WIDTH_BINS = 1
PARTIAL_DECAY = 0.85


def _comb(fundamental_bin: float) -> NDArray[np.float32]:
    """One frame of a harmonic series standing on a fundamental, its partials falling away above it."""
    bins = np.arange(ANALYSIS.band_count, dtype=np.float32)
    frame = np.zeros(ANALYSIS.band_count, dtype=np.float32)
    for harmonic in range(1, HARMONIC_COUNT + 1):
        center = fundamental_bin + ANALYSIS.bins_per_octave * np.log2(harmonic)
        frame += PARTIAL_DECAY**harmonic * np.exp(-0.5 * ((bins - center) / COMB_WIDTH_BINS) ** 2)
    return np.clip(frame / frame.max(), 0.0, 1.0)


def write_frame_cache(directory: Path, *, sample_count: int = CACHED_SAMPLE_COUNT) -> FrameCache:
    """A small cache of harmonic combs, each sample a semitone or two above the last, with a true retuning beside it."""
    generator = np.random.default_rng(0)
    frames = np.zeros((sample_count, READING_COUNT, ANALYSIS.kept_frame_count, ANALYSIS.band_count), dtype=np.float16)
    counts = np.full((sample_count, READING_COUNT), ANALYSIS.kept_frame_count, dtype=np.int16)
    offsets = generator.uniform(-RETUNING_RANGE_SEMITONES, RETUNING_RANGE_SEMITONES, sample_count)
    for position in range(sample_count):
        fundamental_bin = LOWEST_FUNDAMENTAL_BIN + FUNDAMENTAL_STEP_BINS * (position % 12)
        moved = fundamental_bin + ANALYSIS.bins_per_semitone * offsets[position]
        for reading, center in ((STORED_READING, fundamental_bin), (RETUNED_READING, moved)):
            frames[position, reading, :] = _comb(float(center))
    directory.mkdir(parents=True, exist_ok=True)
    np.save(directory / FRAMES_FILE_NAME, frames)
    np.save(directory / COUNTS_FILE_NAME, counts)
    np.save(directory / OFFSETS_FILE_NAME, offsets.astype(np.float32))
    hashes = [format(position + 1, "064x") for position in range(sample_count)]
    (directory / HASHES_FILE_NAME).write_text("\n".join(hashes), encoding="utf-8")
    description = FrameCacheDescription(
        analysis=ANALYSIS,
        sample_count=sample_count,
        retuning_range_semitones=RETUNING_RANGE_SEMITONES,
        random_seed=0,
    )
    (directory / DESCRIPTION_FILE_NAME).write_text(description.model_dump_json(), encoding="utf-8")
    return open_frame_cache(directory)
