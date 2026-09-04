from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from trackmod.core.samples.loop import Loop, LoopMode
from trackmod.core.samples.sample import Sample as TrackModSample
from trackmod.core.samples.vibrato import Vibrato as TrackModVibrato
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.channels import ChannelLayout
from samplecore.models.sample_properties import ITSampleProperties, SampleOccurrence, Vibrato, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from sampleextract.rendering import render_properties, render_sample_pcm

SAMPLE_RATE = 44100
SAMPLE_HASH = "a" * 64
MODULE_HASH = "c" * 64


def probe_waveform(frames: int, *, seed: int) -> NDArray[np.float64]:
    return np.random.default_rng(seed).uniform(-1.0, 1.0, frames)


def test_render_sample_pcm_reshapes_a_mono_waveform_to_two_dimensions() -> None:
    trackmod_sample = TrackModSample(name="s", pcm=probe_waveform(8, seed=1), rate=SAMPLE_RATE)

    sample_pcm = render_sample_pcm(SAMPLE_HASH, trackmod_sample)

    assert sample_pcm.pcm.shape == (8, 1)
    assert sample_pcm.sample.channels is ChannelLayout.MONO


def test_render_sample_pcm_passes_a_stereo_waveform_through_unchanged() -> None:
    left = probe_waveform(8, seed=1)
    right = probe_waveform(8, seed=2)
    trackmod_sample = TrackModSample(name="s", pcm=np.stack([left, right], axis=1), rate=SAMPLE_RATE)

    sample_pcm = render_sample_pcm(SAMPLE_HASH, trackmod_sample)

    assert sample_pcm.pcm.shape == (8, 2)
    assert sample_pcm.sample.channels is ChannelLayout.STEREO
    assert np.array_equal(sample_pcm.pcm, trackmod_sample.pcm)


def test_render_sample_pcm_carries_the_hash_and_shape_onto_the_sample() -> None:
    trackmod_sample = TrackModSample(name="s", pcm=probe_waveform(16, seed=3), rate=SAMPLE_RATE)

    sample_pcm = render_sample_pcm(SAMPLE_HASH, trackmod_sample)

    assert sample_pcm.sample.hash == SAMPLE_HASH
    assert sample_pcm.sample.frames == 16
    assert sample_pcm.sample.depth == trackmod_sample.depth


def test_render_properties_carries_the_xm_tuning_through() -> None:
    trackmod_sample = TrackModSample(
        name="lead",
        pcm=probe_waveform(8, seed=1),
        rate=SAMPLE_RATE,
        volume=40,
        panning=100,
        relative_note=5,
        finetune=-30,
    )
    occurrence = SampleOccurrence(module_hash=MODULE_HASH, instrument_index=0, sample_slot=0)

    properties = render_properties(
        tracker=TrackerFormat.XM, sample_hash=SAMPLE_HASH, occurrence=occurrence, trackmod_sample=trackmod_sample
    )

    assert isinstance(properties, XMSampleProperties)
    assert properties.volume == 40
    assert properties.panning == 100
    assert properties.tuning == Tuning(relative_note=5, finetune=-30)


def test_render_properties_carries_it_specific_fields_through() -> None:
    trackmod_sample = TrackModSample(
        name="kick",
        pcm=probe_waveform(8, seed=2),
        rate=SAMPLE_RATE,
        gain=48,
        sustain_loop=Loop(begin=0, end=8, mode=LoopMode.PING_PONG),
        filename="KICK.WAV",
        vibrato=TrackModVibrato(speed=1, depth=2, rate=3, waveform=0),
    )
    occurrence = SampleOccurrence(module_hash=MODULE_HASH, instrument_index=1, sample_slot=2)

    properties = render_properties(
        tracker=TrackerFormat.IT, sample_hash=SAMPLE_HASH, occurrence=occurrence, trackmod_sample=trackmod_sample
    )

    assert isinstance(properties, ITSampleProperties)
    assert properties.global_volume == 48
    assert properties.sustain_loop == Loop(begin=0, end=8, mode=LoopMode.PING_PONG)
    assert properties.filename == "KICK.WAV"
    assert properties.vibrato == Vibrato(speed=1, depth=2, rate=3, waveform=0)
