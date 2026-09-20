from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from samplecore.tracking.silent import SilentRun
from samplemorph.coordinates.pitch_head.store import NO_CALIBRATION_SEMITONES, load_pitch_head
from samplemorph.model_paths import pitch_head_path
from samplemorph.training.pitch.data import PitchCorpus
from samplemorph.training.pitch.run import pitch_head_shape, run_pitch_training
from samplemorph.training.pitch.settings import PitchTrainingSettings
from samplemorph.training.refusals import ResumeRefused
from samplemorph.training.run_paths import RunFamily
from samplemorph.training.run_settings import RunSettings
from samplemorph.training.runs import RunPlacement
from samplemorph.training.splits import held_out_by_class
from tests.samplemorph.training.pitch.conftest import ANALYSIS, write_frame_cache

HEAD_NAME = "tiny"
VALIDATION_SHARE = 0.25
SHIFT_REACH_SEMITONES = 4.0


def _corpus(library_root: Path) -> PitchCorpus:
    cache = write_frame_cache(library_root / "cache" / "frames" / "tiny")
    held_out = held_out_by_class(cache.hashes, classes={}, share=VALIDATION_SHARE, random_seed=0)
    return PitchCorpus(
        cache=cache,
        library_root=library_root,
        training_positions=np.flatnonzero(~held_out),
        validation_positions=np.flatnonzero(held_out),
    )


def _settings(invariance_weight: float) -> PitchTrainingSettings:
    return PitchTrainingSettings(
        run=RunSettings(epochs=1, batch_size=4, worker_count=0, accelerator="cpu"),
        shift_reach_semitones=SHIFT_REACH_SEMITONES,
        invariance_weight=invariance_weight,
        validation_share=VALIDATION_SHARE,
    )


def _placement(library_root: Path, *, resume: bool) -> RunPlacement:
    return RunPlacement(
        library_root=library_root, family=RunFamily.PITCH, model_name=HEAD_NAME, tracker=SilentRun(), resume=resume
    )


def test_the_head_a_cache_asks_for_reads_its_bins_and_answers_beyond_them_either_way(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)

    shape = pitch_head_shape(corpus, settings=_settings(1.0))

    assert shape.band_count == ANALYSIS.band_count
    assert shape.shift_reach_bins == round(SHIFT_REACH_SEMITONES * ANALYSIS.bins_per_semitone)
    assert shape.output_bins == ANALYSIS.band_count + 2 * shape.shift_reach_bins


def test_a_run_writes_a_head_that_reads_frames_again_with_the_samples_it_was_judged_on(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)

    outcome = run_pitch_training(corpus, settings=_settings(1.0), placement=_placement(tmp_path, resume=False))

    stored = load_pitch_head(pitch_head_path(tmp_path, name=HEAD_NAME), device=torch.device("cpu"))
    assert outcome.exported
    assert stored.description.validation_hashes == corpus.validation_hashes
    assert stored.description.cache == corpus.cache.directory.name
    assert stored.description.analysis == corpus.cache.description.analysis
    assert stored.description.calibration_semitones != NO_CALIBRATION_SEMITONES
    frames = corpus.cache.frames[0, 0].astype(np.float32)
    assert 0.0 <= stored.read_frames(frames).reliability <= 1.0


def test_a_run_resumed_under_another_objective_is_refused(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    run_pitch_training(corpus, settings=_settings(1.0), placement=_placement(tmp_path, resume=False))

    with pytest.raises(ResumeRefused):
        run_pitch_training(corpus, settings=_settings(0.0), placement=_placement(tmp_path, resume=True))
