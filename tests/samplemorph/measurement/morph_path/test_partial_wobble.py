from __future__ import annotations

import math
from typing import Final

import numpy as np

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import log_frequency_geometry
from samplemorph.measurement.morph_path.partial_wobble import WOBBLE_HOP_SECONDS, partial_wobble_cents
from samplemorph.routes.analysis import AnalysisRoute
from samplemorph.routes.kinds import pair_through
from samplemorph.routes.route import HeardMono
from samplemorph.transport.morph import transport
from samplemorph.transport.settings import TransportSettings
from tests.samplemorph.partials.conftest import times, vibrato_tone

RATE_HZ: Final[float] = float(NOMINAL_WAV_RATE)
STEADY_CEILING_CENTS: Final[float] = 0.5
VIBRATO_DEPTH_CENTS: Final[float] = 50.0
VIBRATO_RATE_HZ: Final[float] = 5.5
WINDOW_SHALLOWING: Final[float] = 0.8
CHORD_SECONDS: Final[float] = 1.5
WOBBLE_RATIO_FLOOR: Final[float] = 3.0
C4, E4, G4, F4, A4 = 261.63, 329.63, 392.0, 349.23, 440.0


def _chord(notes: tuple[float, ...]) -> np.ndarray:
    seconds = times(CHORD_SECONDS)
    total = np.sum([np.sin(2.0 * np.pi * k * note * seconds) / k for note in notes for k in range(1, 11)], axis=0)
    return 0.5 * total / np.abs(total).max()


def test_a_steady_tone_barely_moves() -> None:
    tone = np.sum([np.sin(2.0 * np.pi * 220.0 * k * times()) / k for k in range(1, 9)], axis=0)

    assert partial_wobble_cents(tone, rate_hz=RATE_HZ) <= STEADY_CEILING_CENTS


def test_a_vibrato_reads_the_mean_step_its_swing_takes() -> None:
    """A sinusoidal swing of depth d at rate r moves 4 r d cents a second on average."""
    tone = vibrato_tone(
        fundamental_hz=220.0, depth_cents=VIBRATO_DEPTH_CENTS, rate_hz=VIBRATO_RATE_HZ, harmonic_count=8
    )
    expected = 4.0 * VIBRATO_RATE_HZ * VIBRATO_DEPTH_CENTS * WOBBLE_HOP_SECONDS

    reading = partial_wobble_cents(tone, rate_hz=RATE_HZ)

    assert WINDOW_SHALLOWING * expected <= reading <= expected * 1.05


def test_noise_holds_no_partial_to_read() -> None:
    assert math.isnan(partial_wobble_cents(np.random.default_rng(2).normal(size=times().shape[0]), rate_hz=RATE_HZ))


def test_the_transport_midpoint_of_two_chords_wobbles_far_more_than_either_chord() -> None:
    route = AnalysisRoute(path=transport, geometry=log_frequency_geometry(), settings=TransportSettings())
    prepared = pair_through(
        route,
        HeardMono(mono=prepare_mono(_chord((C4, E4, G4))), rate_hz=RATE_HZ),
        HeardMono(mono=prepare_mono(_chord((C4, F4, A4))), rate_hz=RATE_HZ),
    )

    first, middle, second = (
        partial_wobble_cents(prepared.render(weight=weight), rate_hz=RATE_HZ) for weight in (0.0, 0.5, 1.0)
    )

    assert middle >= WOBBLE_RATIO_FLOOR * max(first, second)
