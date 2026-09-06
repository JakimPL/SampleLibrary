from __future__ import annotations

from trackmod.core.samples.sample import Sample as TrackModSample
from trackmod.core.samples.vibrato import Vibrato as TrackModVibrato
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.sample_properties import (
    ITSampleProperties,
    MODSampleProperties,
    S3MSampleProperties,
    SampleOccurrence,
    TrackerSampleProperties,
    Vibrato,
    XMSampleProperties,
)
from samplecore.models.tracker import TrackerFormat


def render_sample_pcm(sample_hash: str, trackmod_sample: TrackModSample) -> SamplePCM:
    """A TrackMod sample's identity and waveform, reshaped onto this library's own conventions.

    TrackMod stores a mono waveform 1-D and a stereo one 2-D; SamplePCM always expects a
    ``(frames, channels)`` array, so a mono waveform gains its own channel axis here and a stereo
    one passes through unchanged.
    """
    channels = ChannelLayout(trackmod_sample.channels)
    sample = Sample(hash=sample_hash, depth=trackmod_sample.depth, channels=channels, frames=trackmod_sample.frames)
    pcm = trackmod_sample.pcm if channels is ChannelLayout.STEREO else trackmod_sample.pcm.reshape(-1, 1)
    return SamplePCM(sample=sample, pcm=pcm)


def render_properties(
    *,
    tracker: TrackerFormat,
    sample_hash: str,
    occurrence: SampleOccurrence,
    trackmod_sample: TrackModSample,
) -> TrackerSampleProperties:
    """One occurrence's tracker-specific properties, read off the TrackMod sample that names it."""
    match tracker:
        case TrackerFormat.XM:
            return _render_xm_properties(sample_hash, occurrence, trackmod_sample)
        case TrackerFormat.IT:
            return _render_it_properties(sample_hash, occurrence, trackmod_sample)
        case TrackerFormat.MOD:
            return _render_mod_properties(sample_hash, occurrence, trackmod_sample)
        case TrackerFormat.S3M:
            return _render_s3m_properties(sample_hash, occurrence, trackmod_sample)


def _render_xm_properties(
    sample_hash: str, occurrence: SampleOccurrence, trackmod_sample: TrackModSample
) -> XMSampleProperties:
    return XMSampleProperties(
        sample_hash=sample_hash,
        occurrence=occurrence,
        name=trackmod_sample.name,
        rate=trackmod_sample.rate,
        volume=trackmod_sample.volume,
        panning=trackmod_sample.panning,
        loop=trackmod_sample.loop,
        tuning=Tuning(relative_note=trackmod_sample.relative_note, finetune=trackmod_sample.finetune),
    )


def _render_it_properties(
    sample_hash: str, occurrence: SampleOccurrence, trackmod_sample: TrackModSample
) -> ITSampleProperties:
    return ITSampleProperties(
        sample_hash=sample_hash,
        occurrence=occurrence,
        name=trackmod_sample.name,
        rate=trackmod_sample.rate,
        volume=trackmod_sample.volume,
        panning=trackmod_sample.panning,
        loop=trackmod_sample.loop,
        global_volume=trackmod_sample.gain,
        sustain_loop=trackmod_sample.sustain_loop,
        filename=trackmod_sample.filename,
        vibrato=_render_vibrato(trackmod_sample.vibrato),
    )


def _render_mod_properties(
    sample_hash: str, occurrence: SampleOccurrence, trackmod_sample: TrackModSample
) -> MODSampleProperties:
    return MODSampleProperties(
        sample_hash=sample_hash,
        occurrence=occurrence,
        name=trackmod_sample.name,
        rate=trackmod_sample.rate,
        volume=trackmod_sample.volume,
        panning=trackmod_sample.panning,
        loop=trackmod_sample.loop,
    )


def _render_s3m_properties(
    sample_hash: str, occurrence: SampleOccurrence, trackmod_sample: TrackModSample
) -> S3MSampleProperties:
    return S3MSampleProperties(
        sample_hash=sample_hash,
        occurrence=occurrence,
        name=trackmod_sample.name,
        rate=trackmod_sample.rate,
        volume=trackmod_sample.volume,
        panning=trackmod_sample.panning,
        loop=trackmod_sample.loop,
        filename=trackmod_sample.filename,
    )


def _render_vibrato(vibrato: TrackModVibrato) -> Vibrato:
    return Vibrato(speed=vibrato.speed, depth=vibrato.depth, rate=vibrato.rate, waveform=vibrato.waveform)
