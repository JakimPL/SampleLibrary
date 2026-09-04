from __future__ import annotations

import numpy as np
import pytest

from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM


def test_pcm_matching_the_declared_shape_is_accepted(mono_sample: Sample) -> None:
    pcm = np.zeros((mono_sample.frames, mono_sample.channels.value), dtype=np.float64)

    sample_pcm = SamplePCM(sample=mono_sample, pcm=pcm)

    assert sample_pcm.pcm.shape == (mono_sample.frames, 1)


def test_a_one_dimensional_waveform_is_rejected(mono_sample: Sample) -> None:
    pcm = np.zeros(mono_sample.frames, dtype=np.float64)

    with pytest.raises(ValueError, match="2-D"):
        SamplePCM(sample=mono_sample, pcm=pcm)


def test_a_frame_count_mismatch_is_rejected(mono_sample: Sample) -> None:
    pcm = np.zeros((mono_sample.frames + 1, mono_sample.channels.value), dtype=np.float64)

    with pytest.raises(ValueError, match="does not match declared"):
        SamplePCM(sample=mono_sample, pcm=pcm)


def test_a_channel_count_mismatch_is_rejected(mono_sample: Sample) -> None:
    pcm = np.zeros((mono_sample.frames, 2), dtype=np.float64)

    with pytest.raises(ValueError, match="does not match declared"):
        SamplePCM(sample=mono_sample, pcm=pcm)
