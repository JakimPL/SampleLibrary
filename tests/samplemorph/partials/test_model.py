from __future__ import annotations

from typing import Final

import numpy as np

from samplemorph.partials.peaks import analysis_length
from tests.samplemorph.partials.conftest import (
    GEOMETRY,
    HOP_LENGTH,
    RATE_HZ,
    SETTINGS,
    harmonics,
    model_of,
    noise_hit,
    times,
    tracks_of,
)

FUNDAMENTAL_HZ: Final[float] = 440.0
HARMONIC_COUNT: Final[int] = 6
STRUCK_AT_SECONDS: Final[float] = 0.5
RISEN_SHARE: Final[float] = 0.1
LARGEST_PRE_ONSET_FRAMES: Final[int] = 5
CLOSE_AMPLITUDE: Final[float] = 0.25
AMPLITUDE_TOLERANCE: Final[float] = 0.1


def test_a_model_holds_one_analysis_of_its_sound_beside_the_partials_it_sounds() -> None:
    model = model_of(harmonics(FUNDAMENTAL_HZ, harmonic_count=HARMONIC_COUNT))

    frames = 1 + model.whole.sample_count // HOP_LENGTH
    assert model.channels.tracks.frame_count == frames
    assert model.whole.frame_count == frames
    assert model.residual.frame_count == frames
    assert model.residual.onset_sample == model.whole.onset_sample
    assert model.rate_hz == RATE_HZ
    assert model.nbytes > model.whole.nbytes


def test_a_partial_rises_no_sooner_than_the_sound_it_belongs_to() -> None:
    """The window a partial is followed on reaches back about its own length, and the spectrum the residual lives on holds it to the strike."""
    struck = np.where(times() >= STRUCK_AT_SECONDS, harmonics(FUNDAMENTAL_HZ, harmonic_count=1), 0.0)
    onset_frame = int(STRUCK_AT_SECONDS * RATE_HZ) // HOP_LENGTH
    reach = analysis_length(RATE_HZ, settings=SETTINGS) // (2 * HOP_LENGTH)

    model = model_of(struck)
    followed = tracks_of(struck)

    steady = float(np.median(model.channels.tracks.amplitude[0, onset_frame + 2 * reach :]))
    held = _risen_frame(model.channels.tracks.amplitude[0], steady=steady)
    assert held > _risen_frame(followed.amplitude[0], steady=steady)
    assert onset_frame - held <= LARGEST_PRE_ONSET_FRAMES


def _risen_frame(amplitude: np.ndarray, *, steady: float) -> int:
    """The first frame a partial stands a tenth of its steady amplitude at."""
    return int(np.flatnonzero(amplitude >= RISEN_SHARE * steady)[0])


def test_a_sound_of_noise_alone_is_its_own_residual() -> None:
    model = model_of(noise_hit(seed=9))

    assert model.channels.tracks.track_count == 0
    assert model.residual.energy is model.whole.energy


def test_two_partials_too_close_for_the_shorter_analysis_keep_their_own_amplitudes() -> None:
    """The shorter analysis reads two neighbors as one louder peak, and each partial keeps the quieter reading of the two."""
    spacing_hz = 1.5 * RATE_HZ / GEOMETRY.fft_length
    seconds = times()
    pair = 0.25 * (
        np.sin(2.0 * np.pi * FUNDAMENTAL_HZ * seconds) + np.sin(2.0 * np.pi * (FUNDAMENTAL_HZ + spacing_hz) * seconds)
    )

    model = model_of(pair)

    middle = slice(model.channels.tracks.frame_count // 4, 3 * model.channels.tracks.frame_count // 4)
    assert model.channels.tracks.track_count == 2
    assert np.allclose(
        np.median(model.channels.tracks.amplitude[:, middle], axis=1), CLOSE_AMPLITUDE, rtol=AMPLITUDE_TOLERANCE
    )
