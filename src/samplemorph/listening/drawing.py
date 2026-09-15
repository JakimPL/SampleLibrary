from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth

from samplecore.auditory.strikes import MAIN_STRIKE_DEPTH_DB, read_strikes
from samplecore.storage.sample_audio import SampleAudio
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.geometry import SEMITONES_PER_OCTAVE
from samplemorph.listening.candidates import Candidate, CatalogCandidates
from samplemorph.listening.heard_pairs import is_audible
from samplemorph.listening.kinds import (
    CROSS_KINDS,
    PERCUSSIVE_KINDS,
    SAME_KINDS,
    SUSTAINED_KINDS,
    TONAL_KINDS,
    SoundKind,
)
from samplemorph.listening.pairs import CatalogPair, DrawnPair, PairEnd, PairSet, RetunedPair
from samplemorph.measurement.comparison import held_out_distance_db, held_out_spectrum
from samplemorph.pipeline import common_rate
from samplemorph.routes.route import hear_in_frame

PAIRS_PER_SAME_KIND: Final[int] = 2
LOOP_PAIR_COUNT: Final[int] = 2
MINIMUM_END_DISTANCE_DB: Final[float] = 6.0
MAXIMUM_DISTANCE_CHECKS: Final[int] = 48
LOOP_MINIMUM_STRIKES: Final[int] = 4
LOW_FIDELITY_MAXIMUM_RATE_HZ: Final[float] = 11025.0
HIGH_FIDELITY_MINIMUM_RATE_HZ: Final[float] = 32000.0
SHORTEST_RETUNING_SEMITONES: Final[float] = 7.0
LONGEST_RETUNING_SEMITONES: Final[float] = 12.0

_logger = logging.getLogger(__name__)

Fits = Callable[[Candidate], bool]


@dataclass(frozen=True)
class SecondsRange:
    """How long, as heard, a sound drawn for one slot may last."""

    shortest: float
    longest: float

    def holds(self, seconds: float) -> bool:
        return self.shortest <= seconds <= self.longest


ONE_SHOT_SECONDS: Final[SecondsRange] = SecondsRange(shortest=0.05, longest=4.0)
SHORT_HIT_SECONDS: Final[SecondsRange] = SecondsRange(shortest=0.05, longest=0.4)
SUSTAIN_SECONDS: Final[SecondsRange] = SecondsRange(shortest=1.5, longest=6.0)
LOOP_SECONDS: Final[SecondsRange] = SecondsRange(shortest=1.0, longest=6.0)


def draw_pairs(connection: Connection, audio: SampleAudio, *, random_seed: int) -> PairSet:
    """Draw the pairs a morph comparison is listened to on, the same pairs for the same seed and catalog.

    Two pairs of each kind of sound, six pairs across kinds, one tonal and one percussive sample
    each heard at two rates, a short hit against a long sustain, two pairs of loops, and a sample
    at a low rate and depth against one at a high rate and depth. Every sample drawn is audible and
    drawn once at most, the two ends of a pair come from different modules and different groups of
    near-duplicates, and they lie at least `MINIMUM_END_DISTANCE_DB` apart as heard, so every pair
    has a way to travel. The log names every slot the catalog leaves empty.

    Raises:
        NoScoringShown: the catalog shows no label scoring to draw by.
    """
    candidates = CatalogCandidates(connection, audio, random_seed=random_seed)
    drawer = PairDrawer(candidates, audio)
    for kind in SAME_KINDS:
        drawer.draw_same_kind(kind, count=PAIRS_PER_SAME_KIND)
    for first, second in CROSS_KINDS:
        drawer.draw_cross_kind(first, second)
    drawer.draw_retuned(TONAL_KINDS, slug="tonal")
    drawer.draw_retuned(PERCUSSIVE_KINDS, slug="percussive")
    drawer.draw_short_against_long()
    drawer.draw_loops(count=LOOP_PAIR_COUNT)
    drawer.draw_low_against_high_fidelity()
    return PairSet(seed=random_seed, experiment_id=candidates.experiment_id, pairs=drawer.pairs)


class PairDrawer:
    """Fills the slots of a draw one after another, keeping every sample to one pair."""

    def __init__(self, candidates: CatalogCandidates, audio: SampleAudio) -> None:
        self._candidates = candidates
        self._audio = audio
        self._pairs: list[DrawnPair] = []
        self._used: set[str] = set()
        self._strike_counts: dict[str, int] = {}
        self._audible: dict[str, bool] = {}

    @property
    def pairs(self) -> tuple[DrawnPair, ...]:
        return tuple(self._pairs)

    def draw_same_kind(self, kind: SoundKind, *, count: int) -> None:
        pool = self._candidates.pool(kind)
        for _ in range(count):
            self._draw_catalog_pair(f"same-{kind.name}", pool, pool, first_fits=_one_shot, second_fits=_one_shot)

    def draw_cross_kind(self, first: SoundKind, second: SoundKind) -> None:
        self._draw_catalog_pair(
            f"cross-{first.name}-{second.name}",
            self._candidates.pool(first),
            self._candidates.pool(second),
            first_fits=_one_shot,
            second_fits=_one_shot,
        )

    def draw_short_against_long(self) -> None:
        self._draw_catalog_pair(
            "short-hit-long-sustain",
            self._merged_pool(PERCUSSIVE_KINDS),
            self._merged_pool(SUSTAINED_KINDS),
            first_fits=lambda candidate: SHORT_HIT_SECONDS.holds(candidate.seconds),
            second_fits=lambda candidate: SUSTAIN_SECONDS.holds(candidate.seconds),
        )

    def draw_loops(self, *, count: int) -> None:
        """Pairs of struck sounds long enough, and struck often enough, to be heard as loops."""
        pool = self._merged_pool(PERCUSSIVE_KINDS)
        for _ in range(count):
            self._draw_catalog_pair("loops", pool, pool, first_fits=self._is_loop, second_fits=self._is_loop)

    def draw_low_against_high_fidelity(self) -> None:
        """An eight-bit sample at a low rate against a sixteen-bit one at a high rate, of one kind where the catalog has both."""
        for kind in SAME_KINDS:
            pool = self._candidates.pool(kind)
            found = self._find_pair(pool, pool, first_fits=_low_fidelity, second_fits=_high_fidelity)
            if found is not None:
                self._add_catalog(f"low-high-fidelity-{kind.name}", *found)
                return
        merged = self._merged_pool(SAME_KINDS)
        self._draw_catalog_pair(
            "low-high-fidelity", merged, merged, first_fits=_low_fidelity, second_fits=_high_fidelity
        )

    def draw_retuned(self, kinds: tuple[SoundKind, ...], *, slug: str) -> None:
        """One sample heard at two rates a fifth to an octave apart: two rates it is declared at, or its own rate and a fifth above."""
        fitting = [
            candidate for candidate in self._merged_pool(kinds) if self._is_free(candidate) and _one_shot(candidate)
        ]
        for candidate in fitting:
            declared = _declared_retuning(candidate.declared_rates_hz)
            if (
                declared is not None
                and ONE_SHOT_SECONDS.holds(candidate.sample.frames / declared[1])
                and self._is_audible(candidate)
            ):
                self._add_retuned(f"retuned-{slug}", candidate, rates_hz=declared)
                return
        for candidate in fitting:
            higher = candidate.rate_hz * 2.0 ** (SHORTEST_RETUNING_SEMITONES / SEMITONES_PER_OCTAVE)
            if ONE_SHOT_SECONDS.holds(candidate.sample.frames / higher) and self._is_audible(candidate):
                self._add_retuned(f"retuned-{slug}", candidate, rates_hz=(candidate.rate_hz, higher))
                return
        _logger.warning("The catalog offers no sample for the retuned-%s slot.", slug)

    def _draw_catalog_pair(
        self,
        slug: str,
        first_pool: tuple[Candidate, ...],
        second_pool: tuple[Candidate, ...],
        *,
        first_fits: Fits,
        second_fits: Fits,
    ) -> None:
        found = self._find_pair(first_pool, second_pool, first_fits=first_fits, second_fits=second_fits)
        if found is None:
            _logger.warning("The catalog offers no pair for the %s slot.", slug)
            return
        self._add_catalog(slug, *found)

    def _find_pair(
        self,
        first_pool: tuple[Candidate, ...],
        second_pool: tuple[Candidate, ...],
        *,
        first_fits: Fits,
        second_fits: Fits,
    ) -> tuple[Candidate, Candidate] | None:
        """The first two free, unrelated, audible candidates that fit their slots and sound far enough apart.

        At most `MAXIMUM_DISTANCE_CHECKS` pairs are listened to, which bounds how much audio a
        slot the catalog can hardly fill reads before it is given up.
        """
        checks = 0
        for first in first_pool:
            if not self._is_free(first) or not first_fits(first) or not self._is_audible(first):
                continue
            first_pcm = self._audio.read(first.sample).pcm
            for second in second_pool:
                if (
                    not self._is_free(second)
                    or first.is_related_to(second)
                    or not second_fits(second)
                    or not self._is_audible(second)
                ):
                    continue
                if checks == MAXIMUM_DISTANCE_CHECKS:
                    return None
                checks += 1
                second_pcm = self._audio.read(second.sample).pcm
                if _heard_distance_db(first, second, pcm=(first_pcm, second_pcm)) >= MINIMUM_END_DISTANCE_DB:
                    return first, second
        return None

    def _add_catalog(self, slug: str, first: Candidate, second: Candidate) -> None:
        self._pairs.append(CatalogPair(name=self._next_name(slug), first=_end(first), second=_end(second)))
        self._used.update((first.sample_hash, second.sample_hash))

    def _add_retuned(self, slug: str, candidate: Candidate, *, rates_hz: tuple[float, float]) -> None:
        self._pairs.append(
            RetunedPair(
                name=self._next_name(slug),
                sample=_end(candidate),
                first_rate_hz=rates_hz[0],
                second_rate_hz=rates_hz[1],
            )
        )
        self._used.add(candidate.sample_hash)

    def _next_name(self, slug: str) -> str:
        return f"{len(self._pairs) + 1:02d}-{slug}"

    def _is_free(self, candidate: Candidate) -> bool:
        return candidate.sample_hash not in self._used

    def _merged_pool(self, kinds: tuple[SoundKind, ...]) -> tuple[Candidate, ...]:
        return tuple(candidate for kind in kinds for candidate in self._candidates.pool(kind))

    def _is_audible(self, candidate: Candidate) -> bool:
        if candidate.sample_hash not in self._audible:
            self._audible[candidate.sample_hash] = is_audible(prepare_mono(self._audio.read(candidate.sample).pcm))
        return self._audible[candidate.sample_hash]

    def _is_loop(self, candidate: Candidate) -> bool:
        if not LOOP_SECONDS.holds(candidate.seconds) or not self._is_audible(candidate):
            return False
        if candidate.sample_hash not in self._strike_counts:
            self._strike_counts[candidate.sample_hash] = _loud_strike_count(
                prepare_mono(self._audio.read(candidate.sample).pcm), sample_rate_hz=int(round(candidate.rate_hz))
            )
        return self._strike_counts[candidate.sample_hash] >= LOOP_MINIMUM_STRIKES


def _heard_distance_db(
    first: Candidate, second: Candidate, *, pcm: tuple[NDArray[np.float64], NDArray[np.float64]]
) -> float:
    """How far apart two candidates sound, as held-out distance in the frame the pair is heard in."""
    rate_hz = common_rate(first.rate_hz, second.rate_hz)
    first_heard = hear_in_frame(pcm[0], rate_hz=first.rate_hz, target_rate_hz=rate_hz)
    second_heard = hear_in_frame(pcm[1], rate_hz=second.rate_hz, target_rate_hz=rate_hz)
    return held_out_distance_db(held_out_spectrum(first_heard.mono), held_out_spectrum(second_heard.mono))


def _end(candidate: Candidate) -> PairEnd:
    return PairEnd(sample_hash=candidate.sample_hash, label=candidate.label)


def _one_shot(candidate: Candidate) -> bool:
    return ONE_SHOT_SECONDS.holds(candidate.seconds)


def _low_fidelity(candidate: Candidate) -> bool:
    return (
        candidate.sample.depth is BitDepth.EIGHT
        and candidate.rate_hz <= LOW_FIDELITY_MAXIMUM_RATE_HZ
        and _one_shot(candidate)
    )


def _high_fidelity(candidate: Candidate) -> bool:
    return (
        candidate.sample.depth is BitDepth.SIXTEEN
        and candidate.rate_hz >= HIGH_FIDELITY_MINIMUM_RATE_HZ
        and _one_shot(candidate)
    )


def _declared_retuning(rates_hz: tuple[float, ...]) -> tuple[float, float] | None:
    """The first two declared rates, lowest first, a fifth to an octave apart."""
    for index, lower in enumerate(rates_hz):
        for higher in rates_hz[index + 1 :]:
            interval = SEMITONES_PER_OCTAVE * float(np.log2(higher / lower))
            if SHORTEST_RETUNING_SEMITONES <= interval <= LONGEST_RETUNING_SEMITONES:
                return lower, higher
    return None


def _loud_strike_count(mono: NDArray[np.float64], *, sample_rate_hz: int) -> int:
    """How many strikes peak within `MAIN_STRIKE_DEPTH_DB` of the clip's own peak."""
    strikes = read_strikes(mono, sample_rate_hz=sample_rate_hz)
    peaks = np.maximum.reduceat(strikes.decibels, strikes.starts)
    return int(np.count_nonzero(peaks >= -MAIN_STRIKE_DEPTH_DB))
