from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final

import numpy as np

from samplemorph.canonicalizers import Canonicalizer
from samplemorph.measurement.comparison import held_out_distance_db, held_out_spectrum
from samplemorph.measurement.corpus import ProbeSample, unrelated_pairs
from samplemorph.vocoders.griffin_lim import GriffinLimVocoder, OraclePhaseVocoder

DEFAULT_UNRELATED_PAIR_COUNT: Final[int] = 300


@unique
class ReconstructionRung(StrEnum):
    """The two ways a canonical image is made audible, which together split where the loss sits.

    `ORACLE_PHASE` hands the synthesis the source's own phase, so what it loses belongs to the
    frequency axis and the grid. `ESTIMATED_PHASE` recovers phase iteratively, so the step between
    the two rungs is what a phase estimate costs -- the number that decides whether a learned
    vocoder is worth training.
    """

    ORACLE_PHASE = "oracle_phase"
    ESTIMATED_PHASE = "estimated_phase"


@dataclass(frozen=True)
class ReconstructionTrial:
    """One sample carried through the representation and back to audio, on one rung."""

    sample_hash: str
    rung: ReconstructionRung
    distance_db: float
    frame_count: int


@dataclass(frozen=True)
class RungSummary:
    """What a whole probe reported on one rung."""

    rung: ReconstructionRung
    trial_count: int
    median_distance_db: float
    upper_decile_distance_db: float
    worst_distance_db: float


@dataclass(frozen=True)
class ReconstructionSummary:
    """How closely one canonicalizer's round trip reproduces the audio it started from.

    `unrelated_distance_db` sets the scale: it is how far apart two samples with nothing to do with
    each other sit, so a round trip well below it preserves far more than the differences a codec
    has to represent.
    """

    canonicalizer_name: str
    unrelated_distance_db: float
    rungs: tuple[RungSummary, ...]

    def rung(self, rung: ReconstructionRung) -> RungSummary:
        """The summary for one rung.

        Raises:
            KeyError: this summary carries no trials on that rung.
        """
        for candidate in self.rungs:
            if candidate.rung is rung:
                return candidate

        raise KeyError(f"no reconstruction trials were recorded on the {rung.value} rung")

    @property
    def phase_estimate_cost_db(self) -> float:
        """What recovering phase costs over being handed it, on the same representation."""
        return (
            self.rung(ReconstructionRung.ESTIMATED_PHASE).median_distance_db
            - self.rung(ReconstructionRung.ORACLE_PHASE).median_distance_db
        )


def reconstruction_trials(
    probes: tuple[ProbeSample, ...], canonicalizer: Canonicalizer
) -> tuple[ReconstructionTrial, ...]:
    """Canonicalize each probe, restore it, and measure both rungs against the original audio."""
    trials = []
    for probe in probes:
        reference = held_out_spectrum(probe.mono)
        spectrogram = canonicalizer.restore(canonicalizer.canonicalize(probe.mono))
        for rung, vocoder in (
            (ReconstructionRung.ORACLE_PHASE, OraclePhaseVocoder(probe.mono)),
            (ReconstructionRung.ESTIMATED_PHASE, GriffinLimVocoder()),
        ):
            rebuilt = vocoder.synthesize(spectrogram)
            trials.append(
                ReconstructionTrial(
                    sample_hash=probe.sample.hash,
                    rung=rung,
                    distance_db=held_out_distance_db(reference, held_out_spectrum(rebuilt)),
                    frame_count=probe.sample.frames,
                )
            )
    return tuple(trials)


def unrelated_distance_db(
    probes: tuple[ProbeSample, ...], *, pair_count: int = DEFAULT_UNRELATED_PAIR_COUNT, random_seed: int
) -> float:
    """The median held-out distance between samples drawn independently of one another."""
    spectra = [held_out_spectrum(probe.mono) for probe in probes]
    pairs = unrelated_pairs(len(spectra), pair_count=pair_count, random_seed=random_seed)
    return float(np.median([held_out_distance_db(spectra[first], spectra[second]) for first, second in pairs]))


def summarize_reconstruction(
    trials: tuple[ReconstructionTrial, ...], *, canonicalizer_name: str, unrelated_distance: float
) -> ReconstructionSummary:
    """Gather trials into one report per rung.

    Raises:
        ValueError: the trials are empty, leaving nothing to summarize.
    """
    if not trials:
        raise ValueError("reconstruction trials are empty, so there is nothing to summarize")

    rungs = []
    for rung in ReconstructionRung:
        on_rung = [trial.distance_db for trial in trials if trial.rung is rung]
        if not on_rung:
            continue
        rungs.append(
            RungSummary(
                rung=rung,
                trial_count=len(on_rung),
                median_distance_db=float(np.median(on_rung)),
                upper_decile_distance_db=float(np.percentile(on_rung, 90)),
                worst_distance_db=float(np.max(on_rung)),
            )
        )
    return ReconstructionSummary(
        canonicalizer_name=canonicalizer_name,
        unrelated_distance_db=unrelated_distance,
        rungs=tuple(rungs),
    )
