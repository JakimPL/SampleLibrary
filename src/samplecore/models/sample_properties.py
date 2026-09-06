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
    slot, so it is not part of the shared base. ``filename`` and ``vibrato`` are this format's own
    DOS filename and sample-level auto-vibrato.
    """

    tracker: Literal[TrackerFormat.IT] = TrackerFormat.IT
    global_volume: Volume
    sustain_loop: Loop | None = None
    filename: str | None = None
    vibrato: Vibrato | None = None


class MODSampleProperties(SampleProperties):
    """The occurrence fields Amiga ProTracker stores beside the shared ones.

    ProTracker's own finetune byte only ever feeds into ``rate`` above -- TrackMod's MOD reader
    derives ``rate`` from it and keeps no separate raw copy, unlike FastTracker 2's ``tuning`` --
    and it stores no per-sample panning, sustain loop, filename, or vibrato of its own. This format
    carries nothing beyond the shared base; the subtype exists only so the discriminated union
    below can still tell a MOD occurrence apart from every other format's.
    """

    tracker: Literal[TrackerFormat.MOD] = TrackerFormat.MOD


class S3MSampleProperties(SampleProperties):
    """The occurrence fields Scream Tracker 3 stores beside the shared ones.

    ``filename`` is this format's own DOS filename, the one field Impulse Tracker's own
    ``ITSampleProperties.filename`` inherited from this format's lineage. Scream Tracker 3 stores
    no per-sample panning, sustain loop, or vibrato of its own.
    """

    tracker: Literal[TrackerFormat.S3M] = TrackerFormat.S3M
    filename: str | None = None


TrackerSampleProperties = Annotated[
    XMSampleProperties | ITSampleProperties | MODSampleProperties | S3MSampleProperties,
    Field(discriminator="tracker"),
]
