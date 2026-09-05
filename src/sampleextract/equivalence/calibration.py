from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly
from sqlalchemy import Connection
from trackmod.binary.pcm.quantise import dequantise, quantise
from trackmod.core.samples.depth import BitDepth

from samplecore.models.relation import RelationType, SampleRelation
from samplecore.storage.repositories.relation import DuckDBSampleRelationRepository
from sampleextract.equivalence.scoring import score_gain_variant, score_resampled_variant

DEFAULT_TRIAL_FRAME_COUNT: Final[int] = 2000
DEFAULT_TRIAL_SAMPLE_RATE: Final[int] = 44100


@dataclass(frozen=True)
class CalibrationTrial:
    """One synthetic pair's ground truth and a scorer's verdict on it, for a human to compare."""

    label: str
    is_genuine_match: bool
    confidence: float
    gain: float | None


def separation_gap(trials: tuple[CalibrationTrial, ...]) -> float:
    """How cleanly a set of trials' genuine matches separate from its non-matches.

    A positive value is the confidence margin between the least-confident genuine match and the
    most-confident non-match -- no overlap at any threshold in between. Zero or negative means some
    non-match scored at or above some genuine match, which a single confidence threshold cannot
    then tell apart.

    Raises:
        ValueError: when `trials` carries no genuine match, no non-match, or neither.
    """
    genuine = [trial.confidence for trial in trials if trial.is_genuine_match]
    non_matches = [trial.confidence for trial in trials if not trial.is_genuine_match]
    if not genuine or not non_matches:
        raise ValueError("separation_gap needs at least one genuine match and one non-match to compare")

    return min(genuine) - max(non_matches)


def _tonal_waveform(frame_count: int, *, sample_rate: int = DEFAULT_TRIAL_SAMPLE_RATE) -> NDArray[np.float64]:
    """A smooth, band-limited synthetic waveform, matching the shape a real tracker sample carries."""
    time = np.arange(frame_count) / sample_rate
    waveform = (
        0.5 * np.sin(2 * np.pi * 220 * time)
        + 0.3 * np.sin(2 * np.pi * 440 * time)
        + 0.2 * np.sin(2 * np.pi * 880 * time)
    )
    return waveform.reshape(-1, 1)


def _gain_variant_trial(
    label: str,
    *,
    is_genuine_match: bool,
    waveforms: tuple[NDArray[np.float64], NDArray[np.float64]],
    depths: tuple[BitDepth, BitDepth],
) -> CalibrationTrial:
    score = score_gain_variant(waveforms[0], waveforms[1], depth_a=depths[0], depth_b=depths[1])
    if score is None:
        return CalibrationTrial(label=label, is_genuine_match=is_genuine_match, confidence=0.0, gain=None)

    return CalibrationTrial(
        label=label, is_genuine_match=is_genuine_match, confidence=score.confidence, gain=score.evidence["gain"]
    )


def gain_variant_calibration_trials(*, gains: tuple[float, ...], rng_seed: int) -> tuple[CalibrationTrial, ...]:
    """Synthetic verdicts spanning every case ``score_gain_variant`` must tell apart: a pure bit-depth
    change, a pure amplification at each of ``gains``, the depth-and-gain compound, and unrelated
    content sharing the candidate shape.

    The reference waveform is scaled down by the largest requested gain first, so that amplifying it
    back up before quantising never clips full-scale PCM -- a clipped compound trial would fail for
    a reason that has nothing to do with the scorer's own gain compensation.
    """
    headroom = max(1.0, max((abs(gain) for gain in gains), default=1.0))
    reference = _tonal_waveform(DEFAULT_TRIAL_FRAME_COUNT) / headroom
    unrelated = np.random.default_rng(rng_seed).uniform(-1.0, 1.0, (DEFAULT_TRIAL_FRAME_COUNT, 1))

    trials = [
        _gain_variant_trial(
            "bit_depth",
            is_genuine_match=True,
            waveforms=(reference, dequantise(quantise(reference, BitDepth.EIGHT), BitDepth.EIGHT)),
            depths=(BitDepth.SIXTEEN, BitDepth.EIGHT),
        ),
        _gain_variant_trial(
            "unrelated",
            is_genuine_match=False,
            waveforms=(reference, unrelated),
            depths=(BitDepth.SIXTEEN, BitDepth.SIXTEEN),
        ),
    ]
    for gain in gains:
        scaled = reference * gain
        trials.append(
            _gain_variant_trial(
                "amplification",
                is_genuine_match=True,
                waveforms=(reference, scaled),
                depths=(BitDepth.SIXTEEN, BitDepth.SIXTEEN),
            )
        )
        trials.append(
            _gain_variant_trial(
                "compound_depth_gain",
                is_genuine_match=True,
                waveforms=(reference, dequantise(quantise(scaled, BitDepth.EIGHT), BitDepth.EIGHT)),
                depths=(BitDepth.SIXTEEN, BitDepth.EIGHT),
            )
        )

    return tuple(trials)


def trailing_trim_calibration_trials(
    *, trailing_frame_counts: tuple[int, ...], rng_seed: int
) -> tuple[CalibrationTrial, ...]:
    """Synthetic verdicts on a genuine pair carrying a trailing silent tail of each length in
    ``trailing_frame_counts``, once each waveform has already been trimmed the way
    ``_WaveformCache`` trims it before either scorer ever sees it -- and one unrelated pair sharing
    the untrimmed shape, trimmed the same way.
    """
    reference = _tonal_waveform(DEFAULT_TRIAL_FRAME_COUNT)
    unrelated = np.random.default_rng(rng_seed).uniform(-1.0, 1.0, (DEFAULT_TRIAL_FRAME_COUNT, 1))

    trials = [
        _gain_variant_trial(
            "unrelated",
            is_genuine_match=False,
            waveforms=(reference, unrelated),
            depths=(BitDepth.SIXTEEN, BitDepth.SIXTEEN),
        )
    ]
    for trailing_frame_count in trailing_frame_counts:
        with_silent_tail = np.pad(reference, ((0, trailing_frame_count), (0, 0)))
        trials.append(
            _gain_variant_trial(
                "trailing_trim",
                is_genuine_match=True,
                waveforms=(reference, with_silent_tail),
                depths=(BitDepth.SIXTEEN, BitDepth.SIXTEEN),
            )
        )

    return tuple(trials)


def resampled_variant_calibration_trials(*, ratios: tuple[float, ...], rng_seed: int) -> tuple[CalibrationTrial, ...]:
    """Synthetic verdicts on a genuine pair resampled by each of ``ratios``, each also carrying a
    gain change, and one unrelated pair sharing a plausible resampled shape.
    """
    reference = _tonal_waveform(DEFAULT_TRIAL_FRAME_COUNT)
    unrelated = np.random.default_rng(rng_seed).uniform(-1.0, 1.0, (int(DEFAULT_TRIAL_FRAME_COUNT * 2), 1))

    trials = [_resampled_variant_trial("unrelated", is_genuine_match=False, waveform_a=reference, waveform_b=unrelated)]
    for ratio in ratios:
        up, down = (int(ratio * 100), 100) if ratio >= 1.0 else (100, int(100 / ratio))
        resampled = resample_poly(reference, up=up, down=down, axis=0) * 1.5
        trials.append(
            _resampled_variant_trial(
                "compound_resample_gain", is_genuine_match=True, waveform_a=reference, waveform_b=resampled
            )
        )

    return tuple(trials)


def _resampled_variant_trial(
    label: str, *, is_genuine_match: bool, waveform_a: NDArray[np.float64], waveform_b: NDArray[np.float64]
) -> CalibrationTrial:
    score = score_resampled_variant(waveform_a, waveform_b)
    if score is None:
        return CalibrationTrial(label=label, is_genuine_match=is_genuine_match, confidence=0.0, gain=None)

    return CalibrationTrial(
        label=label, is_genuine_match=is_genuine_match, confidence=score.confidence, gain=score.evidence["gain"]
    )


def most_marginal_relations(
    connection: Connection, *, relation_type: RelationType, limit: int
) -> tuple[SampleRelation, ...]:
    """The `limit` least-confident stored relations of `relation_type` -- the borderline cases worth
    a human's ear before trusting the threshold that accepted them.
    """
    relations = DuckDBSampleRelationRepository(connection).list_all()
    matching = sorted(
        (relation for relation in relations if relation.relation_type is relation_type),
        key=lambda relation: relation.confidence,
    )
    return tuple(matching[:limit])
