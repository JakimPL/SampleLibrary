from __future__ import annotations

import logging

import torch

from samplemorph.coordinates.pitch_head.shape import PitchHeadShape
from samplemorph.coordinates.pitch_head.store import load_pitch_head, save_pitch_head
from samplemorph.model_paths import pitch_head_path
from samplemorph.training.export import BestEpochExport
from samplemorph.training.metrics import PITCH_MONITORED_METRIC
from samplemorph.training.pitch.calibration import calibrate
from samplemorph.training.pitch.data import PitchCorpus, PitchDataModule
from samplemorph.training.pitch.export import PitchHeadWriter
from samplemorph.training.pitch.module import PitchTrainingModule
from samplemorph.training.pitch.settings import PitchTrainingSettings
from samplemorph.training.runs import RunPlacement, TrainingOutcome, begin_run, fit_and_export

CALIBRATION_DEVICE: str = "cpu"

_logger = logging.getLogger(__name__)


def pitch_head_shape(corpus: PitchCorpus, *, settings: PitchTrainingSettings) -> PitchHeadShape:
    """The head the cache and the settings ask for: the cache's bins read, and room for the widest crop shift either way."""
    analysis = corpus.cache.description.analysis
    return PitchHeadShape(
        band_count=analysis.band_count,
        bins_per_octave=analysis.bins_per_octave,
        shift_reach_bins=max(int(round(settings.shift_reach_semitones * analysis.bins_per_semitone)), 1),
    )


def run_pitch_training(
    corpus: PitchCorpus, *, settings: PitchTrainingSettings, placement: RunPlacement
) -> TrainingOutcome:
    """Teach a pitch head over a cached corpus, writing it as its reading of the held-out retunings improves.

    The best epoch is the one whose reading of a true retuning stands closest to the retuning itself
    while augmentation moves it least, which is the pair of questions the head exists to answer. The
    head that epoch wrote is then calibrated against known tones, so what it reads is a pitch rather
    than a bin.
    """
    data = PitchDataModule(corpus, settings=settings)
    begin_run(
        placement,
        settings=settings.run,
        parameters=settings.as_parameters()
        | {
            "cache": corpus.cache.directory.name,
            "band_count": str(corpus.cache.description.analysis.band_count),
            "bins_per_octave": str(corpus.cache.description.analysis.bins_per_octave),
            "training_sample_count": str(len(corpus.training_positions)),
            "validation_sample_count": str(len(corpus.validation_positions)),
        },
    )
    module = PitchTrainingModule(
        pitch_head_shape(corpus, settings=settings),
        settings=settings,
        frame_range_db=corpus.cache.description.analysis.frame_range_db,
    )
    path = pitch_head_path(corpus.library_root, name=placement.model_name)
    export = BestEpochExport(
        path=path,
        monitored=PITCH_MONITORED_METRIC,
        tracker=placement.tracker,
        writer=PitchHeadWriter(module=module, path=path, corpus=corpus, settings=settings),
    )
    outcome = fit_and_export(module, data, export=export, settings=settings.run, placement=placement)
    _calibrate_stored(corpus, placement=placement)
    return outcome


def _calibrate_stored(corpus: PitchCorpus, *, placement: RunPlacement) -> None:
    """Read the exported head's offset from known tones and write it back beside the weights."""
    path = pitch_head_path(corpus.library_root, name=placement.model_name)
    if not path.is_file():
        return
    head = calibrate(
        load_pitch_head(path, device=torch.device(CALIBRATION_DEVICE)),
        cache=corpus.cache,
        positions=corpus.training_positions,
    )
    save_pitch_head(path, network=head.network, description=head.description)
    _logger.info("Calibrated %s at %+.2f semitones.", placement.model_name, head.description.calibration_semitones)
