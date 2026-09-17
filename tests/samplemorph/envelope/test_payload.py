from __future__ import annotations

import json
import struct
from typing import Final

import numpy as np
import pytest

from samplemorph.envelope.payload import (
    PREFIX_FORMAT,
    PREFIX_LENGTH,
    RESPONSE_FORMAT_VERSION,
    RESPONSE_MAGIC,
    ResponsePayloadError,
    response_from_payload,
    response_payload,
)
from samplemorph.envelope.response import HeldEnd
from tests.samplemorph.envelope.conftest import HeardPair

ANOTHER_VERSION: Final[int] = RESPONSE_FORMAT_VERSION + 1
COEFFICIENT_BYTES_DROPPED: Final[int] = 8


def _with_header(payload: bytes, header: object) -> bytes:
    written = json.dumps(header).encode("utf-8")
    coefficients = payload[PREFIX_LENGTH + struct.unpack(PREFIX_FORMAT, payload[:PREFIX_LENGTH])[2] :]
    prefix = struct.pack(PREFIX_FORMAT, RESPONSE_MAGIC, RESPONSE_FORMAT_VERSION, len(written))
    return b"".join((prefix, written, coefficients))


def _header_of(payload: bytes) -> dict[str, object]:
    header_length = struct.unpack(PREFIX_FORMAT, payload[:PREFIX_LENGTH])[2]
    read: dict[str, object] = json.loads(payload[PREFIX_LENGTH : PREFIX_LENGTH + header_length])
    return read


@pytest.mark.parametrize("held", tuple(HeldEnd), ids=("the first sound held", "the second sound held"))
def test_a_response_reads_back_as_it_was_written(pair: HeardPair, held: HeldEnd) -> None:
    read = response_from_payload(response_payload(pair.response))

    assert read.description == pair.response.description
    assert read.filter_held_to(held).description == pair.response.filter_held_to(held).description
    np.testing.assert_array_equal(
        read.filter_held_to(held).coefficients, pair.response.filter_held_to(held).coefficients
    )


def test_a_payload_opens_with_the_magic_and_the_version_it_was_written_under(pair: HeardPair) -> None:
    magic, version, header_length = struct.unpack(PREFIX_FORMAT, response_payload(pair.response)[:PREFIX_LENGTH])

    assert magic == RESPONSE_MAGIC
    assert version == RESPONSE_FORMAT_VERSION
    assert header_length > 0


def test_the_coefficients_follow_the_header_as_the_two_filters_promise(pair: HeardPair) -> None:
    payload = response_payload(pair.response)
    header_length = struct.unpack(PREFIX_FORMAT, payload[:PREFIX_LENGTH])[2]
    promised = sum(
        pair.response.description.coefficient_count * envelope_filter.description.frame_count
        for envelope_filter in (pair.response.first, pair.response.second)
    )

    assert len(payload) - PREFIX_LENGTH - header_length == promised * np.dtype(np.float32).itemsize


def test_bytes_shorter_than_the_opening_are_refused(pair: HeardPair) -> None:
    with pytest.raises(ResponsePayloadError, match="opens with"):
        response_from_payload(response_payload(pair.response)[: PREFIX_LENGTH - 1])


def test_another_format_is_refused_by_the_magic_it_opens_with(pair: HeardPair) -> None:
    payload = response_payload(pair.response)

    with pytest.raises(ResponsePayloadError, match="morph response opens with"):
        response_from_payload(b"OTHER!" + payload[len(RESPONSE_MAGIC) :])


def test_another_version_is_refused_by_the_version_it_states(pair: HeardPair) -> None:
    payload = response_payload(pair.response)
    header_length = struct.unpack(PREFIX_FORMAT, payload[:PREFIX_LENGTH])[2]
    restated = struct.pack(PREFIX_FORMAT, RESPONSE_MAGIC, ANOTHER_VERSION, header_length)

    with pytest.raises(ResponsePayloadError, match=f"format version {ANOTHER_VERSION}"):
        response_from_payload(restated + payload[PREFIX_LENGTH:])


def test_a_payload_ending_inside_its_header_is_refused(pair: HeardPair) -> None:
    payload = response_payload(pair.response)

    with pytest.raises(ResponsePayloadError, match="ends before"):
        response_from_payload(payload[: PREFIX_LENGTH + 4])


def test_a_header_holding_no_json_is_refused(pair: HeardPair) -> None:
    payload = response_payload(pair.response)
    header_length = struct.unpack(PREFIX_FORMAT, payload[:PREFIX_LENGTH])[2]
    prefix = struct.pack(PREFIX_FORMAT, RESPONSE_MAGIC, RESPONSE_FORMAT_VERSION, header_length)

    with pytest.raises(ResponsePayloadError, match="readable JSON"):
        response_from_payload(prefix + b"{" * header_length + payload[PREFIX_LENGTH + header_length :])


def test_a_header_describing_no_reading_is_refused(pair: HeardPair) -> None:
    header = _header_of(response_payload(pair.response))
    del header["description"]

    with pytest.raises(ResponsePayloadError, match="describes no reading"):
        response_from_payload(_with_header(response_payload(pair.response), header))


def test_a_header_describing_no_filter_for_an_end_is_refused(pair: HeardPair) -> None:
    header = _header_of(response_payload(pair.response))
    del header[HeldEnd.SECOND.value]

    with pytest.raises(ResponsePayloadError, match="no filter holding the second sound"):
        response_from_payload(_with_header(response_payload(pair.response), header))


def test_a_filter_filed_under_the_other_end_is_refused(pair: HeardPair) -> None:
    header = _header_of(response_payload(pair.response))
    header[HeldEnd.FIRST.value] = header[HeldEnd.SECOND.value]

    with pytest.raises(ResponsePayloadError, match="files a filter holding the second sound"):
        response_from_payload(_with_header(response_payload(pair.response), header))


def test_coefficients_ending_before_the_header_promises_are_refused(pair: HeardPair) -> None:
    payload = response_payload(pair.response)

    with pytest.raises(ResponsePayloadError, match="promises"):
        response_from_payload(payload[:-COEFFICIENT_BYTES_DROPPED])
