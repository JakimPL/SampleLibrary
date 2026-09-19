from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from samplecore.tracking.silent import SilentRun
from samplemorph.features.store import load_features
from samplemorph.model_paths import features_path
from samplemorph.training.features.data import FeatureCorpus, held_out_by_class
from samplemorph.training.features.run import run_feature_training
from samplemorph.training.features.settings import FeatureTrainingSettings
from samplemorph.training.refusals import ResumeRefused
from samplemorph.training.run_paths import RunFamily
from samplemorph.training.run_settings import RunSettings
from samplemorph.training.runs import RunPlacement
from tests.samplemorph.training.conftest import BAND_COUNT, TIME_COLUMNS, write_grid_cache

MODEL_NAME = "tiny"
VALIDATION_SHARE = 0.25


def _corpus(library_root: Path) -> FeatureCorpus:
    cache = write_grid_cache(library_root / "cache" / "grids" / "tiny")
    held_out = held_out_by_class(cache.hashes, classes={}, share=VALIDATION_SHARE, random_seed=0)
    return FeatureCorpus(
        cache=cache,
        library_root=library_root,
        training_positions=np.flatnonzero(~held_out),
        validation_positions=np.flatnonzero(held_out),
    )


def _settings(critic_weight: float) -> FeatureTrainingSettings:
    return FeatureTrainingSettings(
        critic_weight=critic_weight,
        run=RunSettings(epochs=1, batch_size=4, worker_count=0, accelerator="cpu"),
        latent_size=4,
        width=4,
        validation_share=VALIDATION_SHARE,
    )


def _placement(library_root: Path, *, resume: bool) -> RunPlacement:
    return RunPlacement(
        library_root=library_root, family=RunFamily.FEATURES, model_name=MODEL_NAME, tracker=SilentRun(), resume=resume
    )


def test_a_run_writes_both_networks_with_the_samples_it_was_judged_on(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)

    outcome = run_feature_training(corpus, settings=_settings(0.5), placement=_placement(tmp_path, resume=False))

    stored = load_features(features_path(tmp_path, name=MODEL_NAME), device=torch.device("cpu"))
    assert outcome.exported
    assert stored.description.validation_hashes == corpus.validation_hashes
    assert stored.description.critic_weight == 0.5
    assert stored.description.cache == corpus.cache.directory.name
    grids = corpus.cache.grids[:3, 0].astype(np.float32)
    assert stored.decode(stored.encode(grids)).shape == (3, BAND_COUNT, TIME_COLUMNS)
    assert stored.score(grids).shape == (3,)


def test_a_run_resumed_under_another_critic_weight_is_refused(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    run_feature_training(corpus, settings=_settings(0.5), placement=_placement(tmp_path, resume=False))

    with pytest.raises(ResumeRefused):
        run_feature_training(corpus, settings=_settings(0.0), placement=_placement(tmp_path, resume=True))
