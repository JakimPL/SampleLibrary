from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from torch import Tensor

from samplemorph.coordinates.frames import frame_analysis
from samplemorph.coordinates.pitch_head.network import PitchNetwork, ToeplitzLinear
from samplemorph.coordinates.pitch_head.readout import read_distribution, read_sound
from samplemorph.coordinates.pitch_head.shape import PitchHeadShape
from samplemorph.coordinates.pitch_head.store import (
    PitchHeadDescription,
    StoredPitchHead,
    calibrated,
    load_pitch_head,
    save_pitch_head,
)

ANALYSIS = frame_analysis()
BAND_COUNT = 64
CHANNELS = (4, 6)
SHIFT_REACH_BINS = 12
BATCH = 3
SHIFT_BINS = 5
MARGIN_BINS = 20
EXACT = 1e-5
HEAD_NAME = "under-test"


def _shape(*, band_count: int = BAND_COUNT) -> PitchHeadShape:
    return PitchHeadShape(
        band_count=band_count,
        bins_per_octave=ANALYSIS.bins_per_octave,
        shift_reach_bins=SHIFT_REACH_BINS,
        channels=CHANNELS,
        kernel_size=5,
    )


def _features_within_the_margin(shape: PitchHeadShape) -> Tensor:
    """Channels whose content stands clear of either end, so a shift of it loses nothing off an edge."""
    torch.manual_seed(0)
    features = torch.zeros(BATCH, shape.channels[-1], shape.band_count)
    features[:, :, MARGIN_BINS : shape.band_count - MARGIN_BINS] = torch.randn(
        BATCH, shape.channels[-1], shape.band_count - 2 * MARGIN_BINS
    )
    return features


def _description(shape: PitchHeadShape, *, calibration_semitones: float) -> PitchHeadDescription:
    return PitchHeadDescription(
        name=HEAD_NAME,
        cache="tiny",
        analysis=ANALYSIS,
        shape=shape,
        calibration_semitones=calibration_semitones,
        trusted_reliability=0.5,
        random_seed=0,
        epochs=1,
        trained_sample_count=8,
        best_validation_error=0.25,
        validation_hashes=(format(1, "064x"),),
        parameters={"epochs": "1"},
    )


def _head(shape: PitchHeadShape, *, calibration_semitones: float = 0.0) -> StoredPitchHead:
    torch.manual_seed(0)
    return StoredPitchHead(
        network=PitchNetwork(shape),
        description=_description(shape, calibration_semitones=calibration_semitones),
        device=torch.device("cpu"),
    )


def test_the_toeplitz_layer_answers_a_shifted_frame_the_same_distance_away() -> None:
    shape = _shape()
    layer = ToeplitzLinear(shape)
    features = _features_within_the_margin(shape)
    moved = torch.roll(features, SHIFT_BINS, dims=-1)

    answer = layer(features)
    moved_answer = layer(moved)

    assert torch.allclose(moved_answer[:, SHIFT_BINS:], answer[:, :-SHIFT_BINS], atol=EXACT)


def test_the_toeplitz_layer_reaches_every_bin_a_crop_can_be_shifted_to() -> None:
    shape = _shape()

    answer = ToeplitzLinear(shape)(_features_within_the_margin(shape))

    assert answer.shape == (BATCH, shape.band_count + 2 * SHIFT_REACH_BINS)


def test_a_network_answers_every_frame_with_a_distribution_over_the_bins() -> None:
    shape = _shape()
    network = PitchNetwork(shape)

    distributions = network(torch.rand(BATCH, shape.band_count))

    assert distributions.shape == (BATCH, shape.output_bins)
    assert torch.allclose(distributions.sum(dim=-1), torch.ones(BATCH), atol=EXACT)


def test_a_reading_places_a_peak_between_two_bins_and_says_how_gathered_it_is() -> None:
    distributions = torch.zeros(2, 32)
    distributions[0, 10] = 0.5
    distributions[0, 11] = 0.5
    distributions[1, :] = 1.0 / 32.0

    readout = read_distribution(distributions, reach_bins=3)

    assert readout.bins[0] == pytest.approx(10.5, abs=EXACT)
    assert readout.mass[0] == pytest.approx(1.0, abs=EXACT)
    assert readout.mass[1] < 0.25


def test_a_sound_s_pitch_is_the_median_its_frames_stand_at_and_a_frame_an_octave_off_lowers_the_agreement() -> None:
    distributions = torch.zeros(1, 4, 64)
    for frame, peak in enumerate((20, 20, 20, 56)):
        distributions[0, frame, peak] = 1.0

    readout = read_sound(distributions, valid=torch.ones(1, 4), reach_bins=3)

    assert readout.bins[0] == pytest.approx(20.0, abs=EXACT)
    assert readout.agreement[0] == pytest.approx(0.75, abs=EXACT)


def test_a_stored_head_is_read_back_with_the_description_that_rebuilds_it(tmp_path: Path) -> None:
    shape = _shape()
    head = _head(shape, calibration_semitones=-3.5)
    path = tmp_path / "pitch.pt"

    save_pitch_head(path, network=head.network, description=head.description)
    reopened = load_pitch_head(path, device=torch.device("cpu"))

    assert reopened.description == head.description
    assert reopened.trusted_reliability == head.trusted_reliability
    frames = np.random.default_rng(0).random((4, shape.band_count)).astype(np.float32)
    assert reopened.read_frames(frames).semitones == pytest.approx(head.read_frames(frames).semitones, abs=EXACT)


def test_a_head_loaded_from_nowhere_is_refused(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no pitch head"):
        load_pitch_head(tmp_path / "missing.pt", device=torch.device("cpu"))


def test_calibrating_a_head_moves_every_reading_by_the_offset_and_leaves_its_weights_alone() -> None:
    shape = _shape()
    head = _head(shape)
    frames = np.random.default_rng(0).random((4, shape.band_count)).astype(np.float32)

    moved = calibrated(head, semitones=7.0)

    assert moved.network is head.network
    assert moved.read_frames(frames).semitones == pytest.approx(head.read_frames(frames).semitones + 7.0, abs=EXACT)
