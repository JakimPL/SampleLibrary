from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from samplecore.cli_support import load_config_or_exit
from sampledescriptor.bundling import bundle_descriptor
from sampledescriptor.model_paths import descriptor_path
from sampledescriptor.pretrained import PRETRAINED_DIRECTORY
from samplelibrary.pipeline.artifacts import read_step_record
from samplelibrary.pipeline.layout import PipelineLayout
from samplelibrary.pipeline.steps.descriptor import DESCRIPTOR

SEALED_OUTPUT: Final[str] = "sealed"


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bundle a trained descriptor with the application, as the one new libraries take."
    )
    parser.add_argument(
        "--descriptor",
        type=Path,
        default=None,
        help="The descriptor file to bundle; the configured library's current one when left out.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Copy a trained descriptor and its manifest into the package, where the wheel picks them up."""
    arguments = _parse_arguments(argv)
    model = arguments.descriptor or _current_descriptor(load_config_or_exit().library_root)
    manifest = bundle_descriptor(model, PRETRAINED_DIRECTORY)
    print(f"Bundled {model} into {PRETRAINED_DIRECTORY}, reading the {manifest.canonicalizer} grid.")


def _current_descriptor(library_root: Path) -> Path:
    """The descriptor the library's last complete build stored.

    Raises:
        SystemExit: the library holds no trained descriptor.
    """
    record = read_step_record(PipelineLayout(library_root).step_record(DESCRIPTOR))
    if record is None or SEALED_OUTPUT not in record.outputs:
        sys.exit(f"The library at {library_root} has no trained descriptor. Run `just rebuild` first.")
    return descriptor_path(library_root, name=Path(record.outputs[SEALED_OUTPUT]).stem)


if __name__ == "__main__":
    main()
