from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from samplemorph.canonicalizers.log_frequency import LogFrequencyCanonicalizer
from samplemorph.geometry import AnalysisWindow, Anchor, LogFrequencyGeometry, log_frequency_geometry
from samplemorph.images import AnalysisSpectrogram
from samplemorph.vocoders.pghi import PghiVocoder
from samplemorph.vocoders.restored import (
    RestoredPghiVocoder,
    RestorerDescription,
    load_restorer,
    restorer_path,
    same_analysis,
    save_restorer,
)
from samplemorph.vocoders.restorer_model import Restorer, RestorerShape
from tests.samplemorph.conftest import TEST_FRAME_COUNT, harmonic_tone

TONE_FREQUENCY_HZ = 330.0
SMALL_SHAPE = RestorerShape(channels=8, kernel_size=3, dilations=(1, 2))
CPU = torch.device("cpu")


def _description(geometry: LogFrequencyGeometry) -> RestorerDescription:
    return RestorerDescription(
        canonicalizer="log_frequency",
        geometry=geometry,
        channels=SMALL_SHAPE.channels,
        kernel_size=SMALL_SHAPE.kernel_size,
        dilations=SMALL_SHAPE.dilations,
        epochs=1,
        trained_sample_count=4,
        best_validation_loss=0.05,
        least_squares_validation_loss=0.08,
    )


def _untrained_vocoder(geometry: LogFrequencyGeometry) -> RestoredPghiVocoder:
    torch.manual_seed(0)
    return RestoredPghiVocoder(model=Restorer(SMALL_SHAPE).eval(), description=_description(geometry), device=CPU)


def _tone_spectrogram(geometry: LogFrequencyGeometry) -> AnalysisSpectrogram:
    canonicalizer = LogFrequencyCanonicalizer(geometry)
    tone = harmonic_tone(2 * TEST_FRAME_COUNT, frequency=TONE_FREQUENCY_HZ)[:, 0]
    return canonicalizer.restore(canonicalizer.canonicalize(tone))


def test_an_untrained_restorer_reads_exactly_as_the_integration_alone() -> None:
    """The restorer starts at the least-squares baseline, so the path reduces to PGHI until it learns."""
    geometry = log_frequency_geometry()
    spectrogram = _tone_spectrogram(geometry)

    restored = _untrained_vocoder(geometry).synthesize(spectrogram)
    integrated = PghiVocoder().synthesize(spectrogram)

    assert restored.shape == integrated.shape
    np.testing.assert_allclose(restored, integrated, rtol=1e-4, atol=1e-6)


def test_a_spectrogram_from_another_grid_is_refused_by_its_analysis() -> None:
    taught = log_frequency_geometry()
    other = log_frequency_geometry(bins_per_octave=taught.bins_per_octave // 2)

    with pytest.raises(ValueError, match="bands per octave"):
        _untrained_vocoder(taught).synthesize(_tone_spectrogram(other))


def test_a_hann_analysis_is_refused_before_the_restorer_reads_it() -> None:
    geometry = log_frequency_geometry()

    with pytest.raises(ValueError, match="hann taper"):
        _untrained_vocoder(geometry).synthesize(
            _tone_spectrogram(log_frequency_geometry(analysis_window=AnalysisWindow.HANN))
        )


def test_the_anchor_alone_does_not_make_another_analysis() -> None:
    loudest = log_frequency_geometry(anchor=Anchor.LOUDEST)
    fundamental = log_frequency_geometry(anchor=Anchor.FUNDAMENTAL)
    coarser = log_frequency_geometry(bins_per_octave=loudest.bins_per_octave // 2)

    assert same_analysis(loudest, fundamental)
    assert not same_analysis(loudest, coarser)


def test_a_saved_restorer_loads_back_with_its_description_and_weights(tmp_path: Path) -> None:
    geometry = log_frequency_geometry()
    torch.manual_seed(0)
    model = Restorer(SMALL_SHAPE)
    with torch.no_grad():
        model.output_projection.bias.fill_(0.01)
    path = restorer_path(tmp_path, name="under-test")

    save_restorer(path, model, _description(geometry))
    loaded = load_restorer(path, device=CPU)

    assert path.parent == tmp_path / "models"
    assert loaded.description == _description(geometry)
    assert loaded.model.shape == SMALL_SHAPE
    for original, restored in zip(model.state_dict().values(), loaded.model.state_dict().values(), strict=True):
        assert torch.equal(original, restored)


def test_a_missing_restorer_is_reported_by_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no restorer is stored"):
        load_restorer(restorer_path(tmp_path, name="absent"), device=CPU)
