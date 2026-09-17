from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.canonicalizers.common import prepare_mono
from samplemorph.envelope.filtering import response_gain
from samplemorph.envelope.payload import RESPONSE_FORMAT_VERSION, response_payload
from samplemorph.envelope.response import HeldEnd, ResponseReading, build_envelope_response
from samplemorph.envelope.settings import EnvelopeSettings
from samplemorph.geometry import log_frequency_geometry
from samplemorph.transport.analysis import analyze
from samplemorph.transport.settings import TransportSettings

FIRST_SECONDS: Final[float] = 0.3
SECOND_SECONDS: Final[float] = 0.45
FIRST_HZ: Final[float] = 220.0
SECOND_HZ: Final[float] = 330.0
LOW_HZ: Final[float] = 55.0
PARTIAL_COUNT: Final[int] = 9
DECAY_PER_SECOND: Final[float] = 6.0
SILENT_SHARE: Final[float] = 0.25
GOLDEN_WEIGHTS: Final[tuple[float, ...]] = (0.0, 0.5, 1.0)


def _voice(seconds: float, *, frequency_hz: float, decay: float) -> NDArray[np.float64]:
    """A decaying harmonic tone with low content and a silent tail, which is what the fixtures probe."""
    frames = int(seconds * NOMINAL_WAV_RATE)
    sounding = int(frames * (1.0 - SILENT_SHARE))
    times = np.arange(sounding) / NOMINAL_WAV_RATE
    partials = sum(
        np.sin(2.0 * np.pi * frequency_hz * harmonic * times) / harmonic for harmonic in range(1, PARTIAL_COUNT + 1)
    )
    low = 0.4 * np.sin(2.0 * np.pi * LOW_HZ * times)
    return np.concatenate(((partials + low) * np.exp(-decay * times), np.zeros(frames - sounding)))


def _write_floats(path: Path, values: NDArray[np.floating]) -> None:
    """Write an array as little-endian single-precision floats, in the order C reads them."""
    path.write_bytes(np.ascontiguousarray(values, dtype=np.float32).tobytes())


def export(output_directory: Path) -> None:
    """Write the fixtures the C++ reader and filter are checked against."""
    output_directory.mkdir(parents=True, exist_ok=True)
    geometry = log_frequency_geometry()
    reading = ResponseReading(geometry=geometry, settings=TransportSettings(), envelope_settings=EnvelopeSettings())
    sounds = {
        HeldEnd.FIRST: prepare_mono(_voice(FIRST_SECONDS, frequency_hz=FIRST_HZ, decay=DECAY_PER_SECOND)),
        HeldEnd.SECOND: prepare_mono(_voice(SECOND_SECONDS, frequency_hz=SECOND_HZ, decay=DECAY_PER_SECOND / 2.0)),
    }
    analyses = {
        held: analyze(mono, rate_hz=NOMINAL_WAV_RATE, geometry=geometry, settings=reading.settings)
        for held, mono in sounds.items()
    }
    response = build_envelope_response(
        analyses[HeldEnd.FIRST], analyses[HeldEnd.SECOND], rate_hz=NOMINAL_WAV_RATE, reading=reading
    )

    (output_directory / "morph_response.bin").write_bytes(response_payload(response))
    for held in HeldEnd:
        for weight in GOLDEN_WEIGHTS:
            name = f"log_gain_{held.value}_w{int(round(weight * 100)):03d}.f32"  # (frames, bins)
            gain = response_gain(response, held=held, weight=weight).astype(np.float64)
            _write_floats(output_directory / name, np.log(gain).T)

    manifest = {
        "format_version": RESPONSE_FORMAT_VERSION,
        "rate_hz": NOMINAL_WAV_RATE,
        "weights": list(GOLDEN_WEIGHTS),
        "description": response.description.model_dump(mode="json"),
        "filters": {held.value: response.filter_held_to(held).description.model_dump(mode="json") for held in HeldEnd},
    }
    (output_directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the morph response fixtures the C++ reader is checked against.")
    parser.add_argument("--output", type=Path, required=True, help="The directory to write the fixtures into.")
    export(parser.parse_args().output)


if __name__ == "__main__":
    main()
