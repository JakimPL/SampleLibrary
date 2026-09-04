from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field
from trackmod.core.samples.loop import Loop
from trackmod.schema.scalars import Panning, Rate, Volume
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index, ModuleHash, SampleHash
from samplecore.models.tracker import TrackerFormat

MAX_VIBRATO_UNIT: Final = 255


class SampleOccurrence(BaseModel):
    """Which one slot, in which one module, a SampleProperties row describes.

    An instrument owns an ordered tuple of samples; ``sample_slot`` is a sample's position in
    that tuple -- the only handle XM or IT gives one occurrence, since neither assigns samples
    their own identifier independent of the instrument that owns them.
    """

    model_config = FROZEN

    module_hash: ModuleHash
    instrument_index: Index
    sample_slot: Index


class SampleProperties(BaseModel):
    """Fields every tracker format this library reads attaches to one occurrence of a Sample."""

    model_config = FROZEN

    sample_hash: SampleHash
    occurrence: SampleOccurrence
    name: str
    rate: Rate
    volume: Volume
    panning: Panning | None = None
    loop: Loop | None = None


class XMSampleProperties(SampleProperties):
    """The occurrence fields FastTracker 2 stores beside the shared ones.

    FastTracker 2 keeps no separate per-sample gain, no sustain loop, and no auto-vibrato on the
    sample itself, so ``tuning`` is the only field this format adds: the raw transposition its own
    header stores, which ``rate`` above was already derived from by TrackMod's XM reader.
    """

    tracker: Literal[TrackerFormat.XM] = TrackerFormat.XM
    tuning: Tuning


class Vibrato(BaseModel):
    """The auto-vibrato an Impulse Tracker sample header carries in its own right.

    Newer instrument-format modules commonly leave this at its silent default and drive vibrato
    from the owning instrument instead, but the sample header field exists regardless of which a
    given module actually relies on, so it is captured here rather than assumed unused.
    """

    model_config = FROZEN

    speed: Annotated[int, Field(ge=0, le=MAX_VIBRATO_UNIT)]
    depth: Annotated[int, Field(ge=0, le=MAX_VIBRATO_UNIT)]
    rate: Annotated[int, Field(ge=0, le=MAX_VIBRATO_UNIT)]
    waveform: Annotated[int, Field(ge=0, le=MAX_VIBRATO_UNIT)]


class ITSampleProperties(SampleProperties):
    """The occurrence fields Impulse Tracker stores beside the shared ones.

    ``global_volume`` is IT's own per-sample gain multiplier; FastTracker 2 has no equivalent
    slot, so it is not part of the shared base. ``filename`` and ``vibrato`` stay unset until
    TrackMod's IT sample parser is extended to expose them.
    """

    tracker: Literal[TrackerFormat.IT] = TrackerFormat.IT
    global_volume: Volume
    sustain_loop: Loop | None = None
    filename: str | None = None
    vibrato: Vibrato | None = None


TrackerSampleProperties = Annotated[XMSampleProperties | ITSampleProperties, Field(discriminator="tracker")]
