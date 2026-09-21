from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import IO, Final

from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from samplecore.storage.atomic import write_atomically
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplemorph.envelope.payload import response_payload
from samplemorph.envelope.response import EnvelopeResponse, ResponseReading, build_envelope_response
from samplemorph.geometry import log_frequency_geometry
from samplemorph.heard import HeardSample, SampleNotCataloged, common_rate, read_heard_sample, require_sample
from samplemorph.routes.route import hear_in_frame
from samplemorph.routes.selection import DEFAULT_SELECTION_PATH, read_route_selection
from samplemorph.transport.analysis import analyze
from samplemorph.transport.settings import TransportSettings

COMMAND_NAME: Final[str] = "response"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands, COMMAND_NAME, summary="Write the filter that carries either of two samples toward the other."
    )
    parser.add_argument("--first", type=str, required=True, help="The sample hash the morph starts from.")
    parser.add_argument("--second", type=str, required=True, help="The sample hash the morph arrives at.")
    parser.add_argument("--output", type=str, required=True, help="The file to write the response into.")
    parser.add_argument(
        "--selection",
        type=Path,
        default=DEFAULT_SELECTION_PATH,
        help="The YAML file naming the envelope settings the response is read under.",
    )


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Write the morph response between two samples, the bytes a reader of any language applies at any weight.

    Both samples and the selection are read before any analysis runs, so a mistyped hash, a sample
    whose files are gone, or a selection this command cannot answer is reported in one line. The
    response holds both filters, so one file serves a morph whichever sample is heard as the one
    being carried.

    Raises:
        SystemExit: either hash names no cataloged sample, a sample none of whose files holds it now,
            or a selection that glides.
    """
    audio = SampleAudio.from_catalog(connection, config.library_root)
    try:
        selection = read_route_selection(Path(arguments.selection))
        if selection.glide is not None:
            raise ValueError(
                "a response filters one sample toward another under a moving envelope, and a glide moves "
                f"its harmonics as well, which no filter holds; this selection glides by {selection.glide}"
            )
        first = read_heard_sample(connection, audio, require_sample(connection, arguments.first))
        second = read_heard_sample(connection, audio, require_sample(connection, arguments.second))
    except (SampleNotCataloged, SampleUnavailableError, ValueError) as error:
        _logger.error("Wrote nothing: %s.", error)
        sys.exit(ExitStatus.REFUSED)

    reading = ResponseReading(
        geometry=log_frequency_geometry(), settings=TransportSettings(), envelope_settings=selection.envelope
    )
    response = _response_between(first, second, reading=reading)
    payload = response_payload(response)
    output = Path(arguments.output)
    write_atomically(output, lambda stream: _write(stream, payload))

    _logger.info(
        "Wrote %d bytes carrying %s against %s, over %d and %d frames, into %s.",
        len(payload),
        first.sample.hash[:12],
        second.sample.hash[:12],
        response.first.description.frame_count,
        response.second.description.frame_count,
        output,
    )


def _response_between(first: HeardSample, second: HeardSample, *, reading: ResponseReading) -> EnvelopeResponse:
    """The response between two cataloged samples, both heard in the frame the faster of them sets."""
    rate_hz = common_rate(first.rate_hz, second.rate_hz)
    heard = tuple(
        hear_in_frame(sample.pcm, rate_hz=sample.rate_hz, target_rate_hz=rate_hz) for sample in (first, second)
    )
    analyses = tuple(analyze(sound.mono, rate_hz=rate_hz, geometry=reading.geometry) for sound in heard)
    return build_envelope_response(analyses[0], analyses[1], rate_hz=rate_hz, reading=reading)


def _write(stream: IO[bytes], payload: bytes) -> None:
    stream.write(payload)
