from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
from matplotlib.figure import Figure

from samplemorph.measurement.pitch.residuals import FIFTH_JUMPS_SEMITONES, OCTAVE_JUMPS_SEMITONES
from samplemorph.measurement.pitch.trials import Trial, TrialKind

PANEL_WIDTH_INCHES: Final[float] = 3.6
PANEL_HEIGHT_INCHES: Final[float] = 2.8
PICTURE_DPI: Final[int] = 110
REACH_SEMITONES: Final[float] = 36.0
BIN_SEMITONES: Final[float] = 0.25
BAR_COLOR: Final[str] = "#3a6ea5"
OCTAVE_COLOR: Final[str] = "#c0392b"
FIFTH_COLOR: Final[str] = "#e67e22"
MARK_ALPHA: Final[float] = 0.6


def draw_residuals(path: Path, trials: tuple[Trial, ...], *, reader: str) -> None:
    """Draw one reader's errors as a histogram per kind of trial, counts on a log scale.

    Octave errors show as bars on the red marks and the other harmonic-series errors, a fifth or a
    twelfth off, on the orange ones; errors beyond ±36 semitones pile into the outermost bins.
    """
    kinds = [kind for kind in TrialKind if any(trial.kind is kind for trial in trials)]
    figure = Figure(figsize=(PANEL_WIDTH_INCHES * max(len(kinds), 1), PANEL_HEIGHT_INCHES), layout="constrained")
    figure.suptitle(f"{reader}: error against the truth, semitones")
    edges = np.arange(-REACH_SEMITONES, REACH_SEMITONES + BIN_SEMITONES, BIN_SEMITONES)
    for axes, kind in zip(np.atleast_1d(figure.subplots(1, max(len(kinds), 1))), kinds, strict=False):
        errors = [error for trial in trials if trial.kind is kind and (error := trial.error_semitones) is not None]
        axes.hist(np.clip(errors, -REACH_SEMITONES, REACH_SEMITONES), bins=edges, color=BAR_COLOR)
        if errors:
            axes.set_yscale("log")
        for jumps, color in ((OCTAVE_JUMPS_SEMITONES, OCTAVE_COLOR), (FIFTH_JUMPS_SEMITONES, FIFTH_COLOR)):
            for jump in jumps:
                if jump < REACH_SEMITONES:
                    for signed in (-jump, jump):
                        axes.axvline(signed, color=color, alpha=MARK_ALPHA, linewidth=0.6, linestyle=":")
        axes.set_title(f"{kind.value}, {len(errors)} read")
        axes.set_xlim(-REACH_SEMITONES, REACH_SEMITONES)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=PICTURE_DPI)
