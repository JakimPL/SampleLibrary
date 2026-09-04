from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.sample_properties import (
    ITSampleProperties,
    SampleOccurrence,
    TrackerSampleProperties,
    XMSampleProperties,
)
from samplecore.models.tracker import TrackerFormat

TRACKER_SAMPLE_PROPERTIES_ADAPTER = TypeAdapter(TrackerSampleProperties)


def _occurrence(module_hash: str) -> SampleOccurrence:
    return SampleOccurrence(module_hash=module_hash, instrument_index=0, sample_slot=0)


def test_xm_sample_properties_carries_its_own_tuning(sample_hash_a: str, module_hash_a: str) -> None:
    properties = XMSampleProperties(
        sample_hash=sample_hash_a,
        occurrence=_occurrence(module_hash_a),
        name="lead",
        rate=8363,
        volume=64,
        tuning=Tuning(relative_note=0, finetune=0),
    )

    assert properties.tracker is TrackerFormat.XM


def test_it_sample_properties_allows_its_optional_fields_to_stay_unset(sample_hash_a: str, module_hash_a: str) -> None:
    properties = ITSampleProperties(
        sample_hash=sample_hash_a,
        occurrence=_occurrence(module_hash_a),
        name="kick",
        rate=8363,
        volume=64,
        global_volume=64,
    )

    assert properties.sustain_loop is None
    assert properties.filename is None
    assert properties.vibrato is None


def test_the_discriminated_union_resolves_each_tracker_to_its_own_type(sample_hash_a: str, module_hash_a: str) -> None:
    xm_payload = {
        "tracker": "xm",
        "sample_hash": sample_hash_a,
        "occurrence": _occurrence(module_hash_a).model_dump(),
        "name": "lead",
        "rate": 8363,
        "volume": 64,
        "tuning": {"relative_note": 0, "finetune": 0},
    }
    it_payload = {
        "tracker": "it",
        "sample_hash": sample_hash_a,
        "occurrence": _occurrence(module_hash_a).model_dump(),
        "name": "kick",
        "rate": 8363,
        "volume": 64,
        "global_volume": 64,
    }

    assert isinstance(TRACKER_SAMPLE_PROPERTIES_ADAPTER.validate_python(xm_payload), XMSampleProperties)
    assert isinstance(TRACKER_SAMPLE_PROPERTIES_ADAPTER.validate_python(it_payload), ITSampleProperties)


def test_an_unknown_tracker_discriminator_is_rejected(sample_hash_a: str, module_hash_a: str) -> None:
    payload = {
        "tracker": "s3m",
        "sample_hash": sample_hash_a,
        "occurrence": _occurrence(module_hash_a).model_dump(),
        "name": "kick",
        "rate": 8363,
        "volume": 64,
    }

    with pytest.raises(ValidationError):
        TRACKER_SAMPLE_PROPERTIES_ADAPTER.validate_python(payload)
