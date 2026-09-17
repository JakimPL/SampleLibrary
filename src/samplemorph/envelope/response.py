from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from samplecore.models.base import FROZEN
from samplemorph.envelope.settings import EnvelopeSettings, Excitation, Timeline
from samplemorph.envelope.split import envelope_cepstrum
from samplemorph.geometry import LogFrequencyGeometry, fourier_bin_count
from samplemorph.transport.analysis import TransportAnalysis, read_magnitude
from samplemorph.transport.morph import FIRST_END_WEIGHT, SECOND_END_WEIGHT
from samplemorph.transport.settings import TransportSettings
from samplemorph.transport.time_map import build_time_map

COEFFICIENT_DTYPE: Final[np.dtype[np.float32]] = np.dtype(np.float32)


@unique
class HeldEnd(StrEnum):
    """Which sound of a pair a filter carries, and whose course through time it holds while it does.

    A filter exists for an end whose own excitation sounds under the moving envelope and whose course
    the path is heard on, which is where the morph is that sound passed through a filter. `FIRST`
    carries the first sound toward the second's envelope, `SECOND` the second toward the first's.
    """

    FIRST = "first"
    SECOND = "second"

    @property
    def timeline(self) -> Timeline:
        """The course an envelope morph holds to read this end exactly as it was analyzed."""
        match self:
            case HeldEnd.FIRST:
                return Timeline.FIRST
            case HeldEnd.SECOND:
                return Timeline.SECOND

    @property
    def excitation(self) -> Excitation:
        """The excitation an envelope morph sounds so that this end's pitch content is the one heard."""
        match self:
            case HeldEnd.FIRST:
                return Excitation.FIRST
            case HeldEnd.SECOND:
                return Excitation.SECOND


@dataclass(frozen=True)
class ResponseReading:
    """How a pair is read for a response: the analysis it is heard through, and the settings that shape it.

    The three travel together because a response means nothing apart from them: the coefficients line
    up with a sound only when it is read through the same analysis, and they draw the envelope the
    envelope settings name.
    """

    geometry: LogFrequencyGeometry
    settings: TransportSettings
    envelope_settings: EnvelopeSettings


class EnvelopeFilterDescription(BaseModel):
    """What one filter of a response says about itself: whose sound it carries, and over how much of it."""

    model_config = FROZEN

    held: HeldEnd
    frame_count: int = Field(ge=1)
    sample_count: int = Field(ge=1)


class EnvelopeResponseDescription(BaseModel):
    """Everything a reader needs to apply a response, beside the coefficients themselves.

    The analysis the coefficients were measured through fixes how a sound must be read for them to
    line up with it: `fft_length` frames, one every `hop_length` samples, of a sound played at
    `rate_hz`, which gives `bin_count` bins. `coefficient_count` and `floor_db` are the two constants
    that draw an envelope, stated so a reader can name the reading the coefficients came from.
    """

    model_config = FROZEN

    coefficient_count: int = Field(ge=1)
    floor_db: float = Field(gt=0.0)
    bin_count: int = Field(ge=1)
    fft_length: int = Field(ge=1)
    hop_length: int = Field(ge=1)
    rate_hz: float = Field(gt=0.0)


@dataclass(frozen=True)
class EnvelopeFilter:
    """One sound carried toward the other's envelope, as the coefficients that draw the gain it takes.

    The morph at any weight is this sound's own spectrum times the envelope ratio raised to how far
    the path has travelled, so the coefficients hold the whole path between the two sounds and a
    weight is one number applied to them. Shape: `coefficients` is ``(coefficient count, frames)``.
    """

    description: EnvelopeFilterDescription
    coefficients: NDArray[np.float32]

    @property
    def held(self) -> HeldEnd:
        return self.description.held

    @property
    def nbytes(self) -> int:
        return int(self.coefficients.nbytes)

    def travel_at(self, weight: float) -> float:
        """How far this filter's sound stands from its own envelope while the morph stands at `weight`.

        A morph runs from the first sound at weight 0 to the second at weight 1, so the end a filter
        holds is the end it sounds untouched at, and the distance grows toward the other end.

        Raises:
            ValueError: the weight lies outside ``[0, 1]``.
        """
        if not FIRST_END_WEIGHT <= weight <= SECOND_END_WEIGHT:
            raise ValueError(f"an envelope morph runs between weights 0 and 1, got {weight}")
        match self.held:
            case HeldEnd.FIRST:
                return weight
            case HeldEnd.SECOND:
                return SECOND_END_WEIGHT - weight


@dataclass(frozen=True)
class EnvelopeResponse:
    """Both filters between one ordered pair of sounds, under one reading of them.

    A pair answers once and a listener moves the weight as often as they like, since every point of
    either path is the held sound times a gain these coefficients draw. Holding both ends means one
    reading serves a morph whichever sound is heard as the one being carried.
    """

    description: EnvelopeResponseDescription
    first: EnvelopeFilter
    second: EnvelopeFilter

    @property
    def nbytes(self) -> int:
        return self.first.nbytes + self.second.nbytes

    def filter_held_to(self, held: HeldEnd) -> EnvelopeFilter:
        """The filter that carries the end named."""
        match held:
            case HeldEnd.FIRST:
                return self.first
            case HeldEnd.SECOND:
                return self.second


def build_envelope_response(
    first: TransportAnalysis, second: TransportAnalysis, *, rate_hz: float, reading: ResponseReading
) -> EnvelopeResponse:
    """Read a pair of analyses as the two filters that carry either sound toward the other's envelope.

    Both sounds are aligned by the transport's own map, once per end so that each end is read exactly
    as it was analyzed while the other is read along it. The difference between the two envelopes'
    coefficients is the whole path: expanding it over the bins and raising it to a weight gives the
    gain the held sound takes at that point. The excitation never enters, since it is the held
    sound's own and divides out.
    """
    description = EnvelopeResponseDescription(
        coefficient_count=reading.envelope_settings.coefficient_count,
        floor_db=reading.envelope_settings.floor_db,
        bin_count=fourier_bin_count(fft_length=reading.geometry.fft_length),
        fft_length=reading.geometry.fft_length,
        hop_length=reading.geometry.hop_length,
        rate_hz=rate_hz,
    )
    return EnvelopeResponse(
        description=description,
        first=_filter_holding(HeldEnd.FIRST, first, second, reading=reading),
        second=_filter_holding(HeldEnd.SECOND, first, second, reading=reading),
    )


def _filter_holding(
    held: HeldEnd, first: TransportAnalysis, second: TransportAnalysis, *, reading: ResponseReading
) -> EnvelopeFilter:
    """The filter that carries the end named, read on that end's own course through time."""
    settings = reading.settings
    time_map = build_time_map(
        first, second, weight=_held_weight(held), hop_length=reading.geometry.hop_length, settings=settings
    )
    first_magnitude = read_magnitude(
        first, positions=time_map.first_positions, rates=time_map.first_rates, settings=settings
    )
    second_magnitude = read_magnitude(
        second, positions=time_map.second_positions, rates=time_map.second_rates, settings=settings
    )
    held_magnitude, far_magnitude = (
        (first_magnitude, second_magnitude) if held is HeldEnd.FIRST else (second_magnitude, first_magnitude)
    )
    coefficients = envelope_cepstrum(far_magnitude, settings=reading.envelope_settings) - envelope_cepstrum(
        held_magnitude, settings=reading.envelope_settings
    )
    return EnvelopeFilter(
        description=EnvelopeFilterDescription(
            held=held, frame_count=time_map.frame_count, sample_count=time_map.sample_count
        ),
        coefficients=coefficients.astype(COEFFICIENT_DTYPE),
    )


def _held_weight(held: HeldEnd) -> float:
    """The weight a time map is built at so the end named is read exactly as it was analyzed."""
    match held:
        case HeldEnd.FIRST:
            return FIRST_END_WEIGHT
        case HeldEnd.SECOND:
            return SECOND_END_WEIGHT
