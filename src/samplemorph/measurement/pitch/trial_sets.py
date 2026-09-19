from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

import numpy as np

from samplemorph.measurement.pitch.reader import ReadPitch
from samplemorph.measurement.pitch.reading import STORED_VARIANT, SampleReadings, SyntheticReadings, Variant
from samplemorph.measurement.pitch.residuals import WITHIN_SEMITONES
from samplemorph.measurement.pitch.synthetic import RenderedTone, TonePair
from samplemorph.measurement.pitch.trials import (
    Question,
    SampleContext,
    Trial,
    TrialKind,
    interval_trial,
    pitch_trial,
)

HASH_PREFIX_LENGTH: Final[int] = 12
DURATION_TERCILES: Final[tuple[str, str, str]] = ("short", "middle", "long")
UNSETTLED_REGISTER: Final[str] = "unsettled"
REFERENCE_NOTE_NUMBER: Final[int] = 69
NOTES_PER_OCTAVE: Final[int] = 12
TERCILE_CUTS: Final[tuple[float, float]] = (1.0 / 3.0, 2.0 / 3.0)


def held_out_trials(
    samples: tuple[SampleReadings, ...],
    *,
    reader_names: tuple[str, ...],
    variants: tuple[Variant, ...],
    referees: tuple[str, str],
) -> tuple[Trial, ...]:
    """Every trial the held-out samples pose to every reader.

    Each variant of a sample is read against the sample as stored, for the interval the variant
    states. Where both referees read the stored sample within half a semitone of each other, every
    reader is also asked to place it where they agree, at the mean of the two, and the octave of that
    pitch is the sample's register; elsewhere the register is unsettled.
    """
    durations = tercile_labels([sample.seconds for sample in samples], labels=DURATION_TERCILES)
    trials: list[Trial] = []
    for sample, duration in zip(samples, durations, strict=True):
        consensus = _consensus(sample, referees=referees)
        context = SampleContext(sound_type=sample.sound_type, duration=duration, register=_register(consensus))
        source = sample.sample_hash[:HASH_PREFIX_LENGTH]
        for variant in variants:
            question = Question(
                kind=variant.kind,
                group=variant.name,
                source=source,
                expected_semitones=variant.expected_semitones,
                context=context,
            )
            trials.extend(
                interval_trial(
                    question,
                    reader=name,
                    reference=sample.readings[(STORED_VARIANT, name)],
                    probe=sample.readings[(variant.name, name)],
                )
                for name in reader_names
            )
        if consensus is not None:
            question = Question(
                kind=TrialKind.CONSENSUS,
                group="+".join(referees),
                source=source,
                expected_semitones=consensus,
                context=context,
            )
            trials.extend(
                pitch_trial(question, reader=name, reading=sample.readings[(STORED_VARIANT, name)])
                for name in reader_names
            )
    return tuple(trials)


def family_trials(
    tones: tuple[RenderedTone, ...], readings: Mapping[str, SyntheticReadings], *, reader_names: tuple[str, ...]
) -> tuple[Trial, ...]:
    """Every reader asked where each synthetic tone sounds, gathered by family and rendering."""
    return tuple(
        pitch_trial(
            Question(
                kind=TrialKind.FAMILY,
                group=tone.group,
                source=tone.name,
                expected_semitones=tone.truth_semitones,
                context=None,
            ),
            reader=name,
            reading=readings[tone.name].readings[name],
        )
        for tone in tones
        for name in reader_names
    )


def pair_trials(
    pairs: tuple[TonePair, ...], readings: Mapping[str, SyntheticReadings], *, reader_names: tuple[str, ...]
) -> tuple[Trial, ...]:
    """Every reader asked how far apart two tones of different timbres sound, gathered by the size of the interval."""
    return tuple(
        interval_trial(
            Question(
                kind=TrialKind.PAIR,
                group=f"{abs(pair.interval_semitones):g}",
                source=pair.name,
                expected_semitones=pair.interval_semitones,
                context=None,
            ),
            reader=name,
            reference=readings[pair.first.name].readings[name],
            probe=readings[pair.second.name].readings[name],
        )
        for pair in pairs
        for name in reader_names
    )


def tercile_labels(values: Sequence[float], *, labels: tuple[str, str, str]) -> tuple[str, ...]:
    """Each value's tercile among all of them, named by `labels` from the lowest; a value on a cut falls below it."""
    if not values:
        return ()
    cuts = np.quantile(np.asarray(values, dtype=np.float64), TERCILE_CUTS)
    return tuple(labels[int(np.searchsorted(cuts, value, side="left"))] for value in values)


def _consensus(sample: SampleReadings, *, referees: tuple[str, str]) -> float | None:
    """Where both referees place the stored sample, when both read it within half a semitone of each other."""
    first, second = (_stored_reading(sample, reader=referee) for referee in referees)
    if first is None or second is None or abs(first.semitones - second.semitones) > WITHIN_SEMITONES:
        return None
    return 0.5 * (first.semitones + second.semitones)


def _stored_reading(sample: SampleReadings, *, reader: str) -> ReadPitch | None:
    return sample.readings.get((STORED_VARIANT, reader))


def _register(consensus: float | None) -> str:
    """The octave a settled pitch lies in, named by the C it starts from in scientific pitch notation."""
    if consensus is None:
        return UNSETTLED_REGISTER
    note_number = int(round(REFERENCE_NOTE_NUMBER + consensus))
    return f"C{note_number // NOTES_PER_OCTAVE - 1}"
