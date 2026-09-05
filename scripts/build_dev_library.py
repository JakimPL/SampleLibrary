from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly
from trackmod.core.instruments.instrument import Instrument
from trackmod.core.instruments.keymap import pitched_keymap
from trackmod.core.patterns.grid import Pattern
from trackmod.core.samples.depth import BitDepth
from trackmod.core.samples.sample import Sample as TrackModSample
from trackmod.core.songs.order import OrderList
from trackmod.core.songs.playback import Playback
from trackmod.core.songs.song import Song
from trackmod.limits.compliance import Compliance
from trackmod.trackers.it.module import ITModule
from trackmod.trackers.xm.module import XMModule

SAMPLE_RATE: Final[int] = 44100
DEFAULT_OUTPUT_DIRECTORY: Final[Path] = Path("dev-library")
MODULES_DIRECTORY_NAME: Final[str] = "modules"
CATALOG_DIRECTORY_NAME: Final[str] = "catalog"

# Below LibraryConfig.minimum_sample_frames' own default (512), so a sample this short is the
# ingestion-time frame filter's own test case, not an oversight here.
TOO_SHORT_SAMPLE_FRAMES: Final[int] = 100


HARMONIC_COUNT: Final[int] = 5


def _tonal_waveform(frame_count: int, *, frequency: float, seed: int) -> NDArray[np.float64]:
    """A smooth, band-limited waveform: `HARMONIC_COUNT` harmonics of `frequency`, at random relative
    weights and phases drawn from `seed`.

    A fixed harmonic ratio is not enough to keep unrelated scenarios apart: two tones sharing the
    same relative harmonic weights are, at some resampling ratio, numerically indistinguishable --
    resampling scales every harmonic by the same factor, so it can reproduce one tone's frequency
    from another's exactly. Randomising the weights per `seed` instead gives each scenario its own
    spectral shape, which a resampling ratio cannot reproduce from a different scenario's shape, so
    independently seeded waveforms stay apart under the same fingerprint search this library's own
    detectors use. A deliberate pair still shares one identical waveform (weights included) before
    its own transformation is applied, so the relationship a pair is built to demonstrate is
    unaffected.
    """
    time = np.arange(frame_count) / SAMPLE_RATE
    random_generator = np.random.default_rng(seed)
    harmonics = np.arange(1, HARMONIC_COUNT + 1)
    weights = random_generator.uniform(0.2, 1.0, size=harmonics.shape)
    weights /= np.sum(weights)
    phases = random_generator.uniform(0.0, 2 * np.pi, size=harmonics.shape)
    tone: NDArray[np.float64] = np.zeros(frame_count)
    for harmonic, weight, phase in zip(harmonics, weights, phases):
        tone += weight * np.sin(2 * np.pi * frequency * harmonic * time + phase)

    return tone


def _resample_stable_waveform(frame_count: int, *, frequency: float) -> NDArray[np.float64]:
    """A waveform for the resampled-variant pair specifically, whose harmonic shape is fixed rather
    than randomised, at this function's own default frequency (440 Hz, matching the call site below).

    Checked empirically while building this corpus: `compute_fingerprint`'s candidate-generation
    similarity depends on more than the resampling ratio alone -- this exact three-harmonic ratio
    stays above the 0.95 candidate-generation threshold at 440 Hz (matching
    `tests/sampleextract/equivalence/test_fingerprint.py`'s own proof of that), a random
    harmonic-weight distribution fell well under it regardless of frequency, and even this fixed
    ratio fell under it at a different frequency tried while building this corpus (990 Hz) -- the
    confirmatory scorer still matched every one of these correctly once compared directly, so this
    is a fragility of the coarse candidate-generation prefilter, not the underlying detection. The
    resampled pair needs to survive candidate generation to demonstrate anything, so it keeps to the
    frequency already verified to.
    """
    time = np.arange(frame_count) / SAMPLE_RATE
    return (
        0.5 * np.sin(2 * np.pi * frequency * time)
        + 0.3 * np.sin(2 * np.pi * frequency * 2 * time)
        + 0.2 * np.sin(2 * np.pi * frequency * 4 * time)
    )


def _single_instrument_song(sample: TrackModSample) -> Song:
    instrument = Instrument(name=sample.name, keymap=pitched_keymap(sample=0))
    return Song(
        name=sample.name,
        channels=1,
        patterns=(Pattern.empty(rows=1, channels=1),),
        order=OrderList(entries=(0,)),
        instruments=(instrument,),
        samples=(sample,),
        playback=Playback(speed=6, tempo=125),
    )


def _multi_instrument_song(name: str, samples: tuple[TrackModSample, ...]) -> Song:
    instruments = tuple(
        Instrument(name=sample.name, keymap=pitched_keymap(sample=index)) for index, sample in enumerate(samples)
    )
    return Song(
        name=name,
        channels=len(samples),
        patterns=(Pattern.empty(rows=1, channels=len(samples)),),
        order=OrderList(entries=(0,)),
        instruments=instruments,
        samples=samples,
        playback=Playback(speed=6, tempo=125),
    )


def _xm_bytes(song: Song) -> bytes:
    return XMModule.from_song(song, compliance=Compliance.EXTENDED).to_bytes()


def _it_bytes(song: Song) -> bytes:
    return ITModule.from_song(song, compliance=Compliance.EXTENDED).to_bytes()


def _normal_modules() -> dict[str, bytes]:
    """Two ordinary, unrelated modules -- one per tracker format -- for a browsable-feeling library
    alongside the deliberately related pairs below.
    """
    xm_samples = (
        TrackModSample(name="lead", pcm=_tonal_waveform(3000, frequency=330.0, seed=1), rate=SAMPLE_RATE),
        TrackModSample(name="bass", pcm=_tonal_waveform(2200, frequency=110.0, seed=2), rate=SAMPLE_RATE),
    )
    it_samples = (
        TrackModSample(name="pad", pcm=_tonal_waveform(4000, frequency=523.0, seed=3), rate=SAMPLE_RATE),
        TrackModSample(name="pluck", pcm=_tonal_waveform(1800, frequency=659.0, seed=4), rate=SAMPLE_RATE),
    )
    return {
        "normal_song.xm": _xm_bytes(_multi_instrument_song("normal_song_xm", xm_samples)),
        "normal_song.it": _it_bytes(_multi_instrument_song("normal_song_it", it_samples)),
    }


def _bit_depth_pair() -> dict[str, bytes]:
    """The same content stored at two depths -- a genuine ``BIT_DEPTH_VARIANT`` once ingested."""
    waveform = _tonal_waveform(2500, frequency=440.0, seed=5)
    sixteen_bit = TrackModSample(name="depth_16", pcm=waveform, rate=SAMPLE_RATE, depth=BitDepth.SIXTEEN)
    eight_bit = TrackModSample(name="depth_8", pcm=waveform, rate=SAMPLE_RATE, depth=BitDepth.EIGHT)
    return {
        "pair_bit_depth_a.xm": _xm_bytes(_single_instrument_song(sixteen_bit)),
        "pair_bit_depth_b.xm": _xm_bytes(_single_instrument_song(eight_bit)),
    }


def _amplification_pair() -> dict[str, bytes]:
    """The same content at two gains, same depth -- a genuine, pure ``AMPLIFICATION_VARIANT``."""
    waveform = _tonal_waveform(2800, frequency=550.0, seed=6)
    original = TrackModSample(name="gain_1x", pcm=waveform, rate=SAMPLE_RATE)
    quieter = TrackModSample(name="gain_half", pcm=waveform * 0.5, rate=SAMPLE_RATE)
    return {
        "pair_amplification_a.xm": _xm_bytes(_single_instrument_song(original)),
        "pair_amplification_b.xm": _xm_bytes(_single_instrument_song(quieter)),
    }


def _compound_pair() -> dict[str, bytes]:
    """Both depth and gain differ at once -- the compound case a gain-insensitive scorer would miss,
    now an ``AMPLIFICATION_VARIANT`` with ``depth_changed`` set in its evidence.
    """
    waveform = _tonal_waveform(2600, frequency=660.0, seed=7)
    original = TrackModSample(name="compound_original", pcm=waveform, rate=SAMPLE_RATE, depth=BitDepth.SIXTEEN)
    quieter_and_requantised = TrackModSample(
        name="compound_variant", pcm=waveform * 0.4, rate=SAMPLE_RATE, depth=BitDepth.EIGHT
    )
    return {
        "pair_compound_a.xm": _xm_bytes(_single_instrument_song(original)),
        "pair_compound_b.xm": _xm_bytes(_single_instrument_song(quieter_and_requantised)),
    }


def _resampled_pair() -> dict[str, bytes]:
    """The same content at two sample rates -- a genuine ``RESAMPLED_VARIANT``."""
    original = _resample_stable_waveform(4410, frequency=440.0)
    resampled = resample_poly(original, up=1, down=2)
    return {
        "pair_resampled_a.xm": _xm_bytes(
            _single_instrument_song(TrackModSample(name="resampled_original", pcm=original, rate=SAMPLE_RATE))
        ),
        "pair_resampled_b.xm": _xm_bytes(
            _single_instrument_song(TrackModSample(name="resampled_variant", pcm=resampled, rate=SAMPLE_RATE))
        ),
    }


def _trailing_trim_pair() -> dict[str, bytes]:
    """The same content, one carrying a genuinely silent trailing tail -- classified as an
    ``AMPLIFICATION_VARIANT`` at gain 1.0 rather than a ``BIT_DEPTH_VARIANT``, since neither depth
    nor audible gain actually changed.
    """
    waveform = _tonal_waveform(2000, frequency=770.0, seed=9)
    with_silent_tail = np.pad(waveform, (0, 20))
    return {
        "pair_trailing_trim_a.xm": _xm_bytes(
            _single_instrument_song(TrackModSample(name="trim_original", pcm=waveform, rate=SAMPLE_RATE))
        ),
        "pair_trailing_trim_b.xm": _xm_bytes(
            _single_instrument_song(TrackModSample(name="trim_with_tail", pcm=with_silent_tail, rate=SAMPLE_RATE))
        ),
    }


def _too_short_module() -> dict[str, bytes]:
    """A sample below the ingestion-time frame filter's floor -- never catalogued at all."""
    too_short = TrackModSample(
        name="too_short", pcm=_tonal_waveform(TOO_SHORT_SAMPLE_FRAMES, frequency=880.0, seed=10), rate=SAMPLE_RATE
    )
    return {"too_short.xm": _xm_bytes(_single_instrument_song(too_short))}


def _all_modules() -> dict[str, bytes]:
    modules: dict[str, bytes] = {}
    for builder in (
        _normal_modules,
        _bit_depth_pair,
        _amplification_pair,
        _compound_pair,
        _resampled_pair,
        _trailing_trim_pair,
        _too_short_module,
    ):
        modules.update(builder())

    return modules


def _write_config(output_directory: Path, *, modules_directory: Path, catalog_directory: Path) -> None:
    config_path = output_directory / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{modules_directory.resolve().as_posix()}"\n'
        f'library_root = "{catalog_directory.resolve().as_posix()}"\n',
        encoding="utf-8",
    )


def build_dev_library(output_directory: Path) -> tuple[Path, ...]:
    """(Re)generates the deterministic dev-module corpus and its own ready-to-use ``config.toml``.

    ``modules_directory`` is wiped and rewritten every call, so this stays safe to rerun whenever
    the scenarios change; ``catalog_directory`` is left untouched, since a developer may still want
    the catalog a prior extraction run built from it.
    """
    modules_directory = output_directory / MODULES_DIRECTORY_NAME
    catalog_directory = output_directory / CATALOG_DIRECTORY_NAME
    if modules_directory.is_dir():
        shutil.rmtree(modules_directory)
    modules_directory.mkdir(parents=True)
    catalog_directory.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    for filename, data in _all_modules().items():
        path = modules_directory / filename
        path.write_bytes(data)
        written_paths.append(path)

    _write_config(output_directory, modules_directory=modules_directory, catalog_directory=catalog_directory)
    return tuple(written_paths)


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a small, deterministic tracker-module corpus for fast local development, "
        "deliberately covering every equivalence-detection relation type."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_DIRECTORY, help="Where to write the corpus and its config.toml."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = _parse_arguments(argv)
    written_paths = build_dev_library(arguments.output)
    print(f"Wrote {len(written_paths)} modules and config.toml under {arguments.output.resolve()}")


if __name__ == "__main__":
    main()
