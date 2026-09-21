from __future__ import annotations

import json
import struct
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import ValidationError

from samplemorph.envelope.response import (
    COEFFICIENT_DTYPE,
    EnvelopeFilter,
    EnvelopeFilterDescription,
    EnvelopeResponse,
    EnvelopeResponseDescription,
    HeldEnd,
)

RESPONSE_MAGIC: Final[bytes] = b"SMORPH"
RESPONSE_FORMAT_VERSION: Final[int] = 1
PREFIX_FORMAT: Final[str] = "<6sHI"
PREFIX_LENGTH: Final[int] = struct.calcsize(PREFIX_FORMAT)
COEFFICIENT_BYTES: Final[int] = COEFFICIENT_DTYPE.itemsize


class ResponsePayloadError(ValueError):
    """Raised when bytes do not hold a morph response this process can read."""


def response_payload(response: EnvelopeResponse) -> bytes:
    """One morph response as the bytes a reader of any language parses.

    The bytes open with the magic, the format version and the length of a JSON header, which states
    the reading the coefficients were measured through and what each of the two filters covers. The
    coefficients follow the header as little-endian single-precision floats, the first sound's
    filter then the second's, each of them one row per coefficient across the frames it covers, so
    the block a filter holds is as long as its own count of coefficients and frames says.
    """
    header = json.dumps(
        {
            "description": response.description.model_dump(mode="json"),
            HeldEnd.FIRST.value: response.first.description.model_dump(mode="json"),
            HeldEnd.SECOND.value: response.second.description.model_dump(mode="json"),
        },
        sort_keys=True,
    ).encode("utf-8")
    prefix = struct.pack(PREFIX_FORMAT, RESPONSE_MAGIC, RESPONSE_FORMAT_VERSION, len(header))
    blocks = (_block(response.first), _block(response.second))
    return b"".join((prefix, header, *blocks))


def response_from_payload(payload: bytes) -> EnvelopeResponse:
    """The morph response bytes hold.

    Raises:
        ResponsePayloadError: the bytes carry another format or version, end before what the header
            promises, or hold a header this process cannot read.
    """
    header, coefficients = _split(payload)
    description = _response_description(header)
    first, read = _filter_from(header, coefficients, held=HeldEnd.FIRST, description=description, offset=0)
    second, read = _filter_from(header, coefficients, held=HeldEnd.SECOND, description=description, offset=read)
    if read != len(coefficients):
        raise ResponsePayloadError(f"the coefficients run {len(coefficients)} bytes where the header promises {read}")
    return EnvelopeResponse(description=description, first=first, second=second)


def _block(envelope_filter: EnvelopeFilter) -> bytes:
    return np.ascontiguousarray(envelope_filter.coefficients, dtype=COEFFICIENT_DTYPE).tobytes()


def _split(payload: bytes) -> tuple[dict[str, object], bytes]:
    """The header a payload states and the coefficient bytes after it.

    Raises:
        ResponsePayloadError: the bytes carry another format or version, or end inside the header.
    """
    if len(payload) < PREFIX_LENGTH:
        raise ResponsePayloadError(f"a morph response opens with {PREFIX_LENGTH} bytes, and these are {len(payload)}")
    magic, version, header_length = struct.unpack(PREFIX_FORMAT, payload[:PREFIX_LENGTH])
    if magic != RESPONSE_MAGIC:
        raise ResponsePayloadError(
            f"these bytes open with {magic!r}, and a morph response opens with {RESPONSE_MAGIC!r}"
        )
    if version != RESPONSE_FORMAT_VERSION:
        raise ResponsePayloadError(
            f"this payload states format version {version}, and this process reads {RESPONSE_FORMAT_VERSION}"
        )
    header_end = PREFIX_LENGTH + header_length
    if len(payload) < header_end:
        raise ResponsePayloadError(f"the header runs {header_length} bytes, and the payload ends before it does")
    try:
        header = json.loads(payload[PREFIX_LENGTH:header_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResponsePayloadError(f"the header holds no readable JSON ({error})") from error
    if not isinstance(header, dict):
        raise ResponsePayloadError("the header holds no object naming the response")
    return header, payload[header_end:]


def _response_description(header: dict[str, object]) -> EnvelopeResponseDescription:
    """What the header says the coefficients were read through.

    Raises:
        ResponsePayloadError: the header names no reading this process understands.
    """
    try:
        return EnvelopeResponseDescription.model_validate(header["description"])
    except (KeyError, ValidationError) as error:
        raise ResponsePayloadError(f"the header describes no reading ({error})") from error


def _filter_from(
    header: dict[str, object],
    coefficients: bytes,
    *,
    held: HeldEnd,
    description: EnvelopeResponseDescription,
    offset: int,
) -> tuple[EnvelopeFilter, int]:
    """One filter read from the block at `offset`, and where the block after it begins.

    Raises:
        ResponsePayloadError: the header describes this filter in a way this process cannot read, or
            the block it promises reaches past the bytes given.
    """
    try:
        filter_description = EnvelopeFilterDescription.model_validate(header[held.value])
    except (KeyError, ValidationError) as error:
        raise ResponsePayloadError(
            f"the header describes no filter holding the {held.value} sound ({error})"
        ) from error
    if filter_description.held is not held:
        raise ResponsePayloadError(
            f"the header files a filter holding the {filter_description.held.value} sound under the {held.value} one"
        )
    shape = (description.coefficient_count, filter_description.frame_count)
    end = offset + shape[0] * shape[1] * COEFFICIENT_BYTES
    if len(coefficients) < end:
        raise ResponsePayloadError(
            f"the {held.value} sound's filter promises {end - offset} bytes of coefficients, and the payload holds "
            f"{len(coefficients) - offset} of them"
        )
    read: NDArray[np.float32] = np.frombuffer(
        coefficients, dtype=COEFFICIENT_DTYPE, count=shape[0] * shape[1], offset=offset
    )
    return EnvelopeFilter(description=filter_description, coefficients=read.reshape(shape)), end
