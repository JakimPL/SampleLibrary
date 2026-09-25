from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from samplecore.cli_support import load_config_or_exit
from samplecore.storage.atomic import copy_atomically
from sampledescriptor.model_paths import descriptor_path
from sampledescriptor.paths import PRETRAINED_RELEASE_PATH
from sampledescriptor.pretrained import write_pretrained_release
from sampledescriptor.releasing import release_of
from samplelibrary.pipeline.artifacts import read_step_record
from samplelibrary.pipeline.layout import PipelineLayout
from samplelibrary.pipeline.steps.descriptor import DESCRIPTOR

SEALED_OUTPUT: Final[str] = "sealed"
UPLOAD_DIRECTORY: Final[Path] = Path("dist") / "descriptor"
RELEASE_DOWNLOAD_URL: Final[str] = "https://github.com/JakimPL/SampleLibrary/releases/download/{tag}/{name}"


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a trained descriptor for publishing as the one new libraries download."
    )
    parser.add_argument(
        "--tag", type=str, required=True, help="The GitHub release to upload it to, such as descriptor-1."
    )
    parser.add_argument(
        "--descriptor",
        type=Path,
        default=None,
        help="The descriptor file to publish; the configured library's current one when left out.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Write a trained descriptor's file to upload, and the release record new libraries download it by.

    The file goes into `dist/descriptor/`, for the GitHub release the tag names. The record names its
    download URL, digest and grid, and belongs in a commit with the code that reads it.
    """
    arguments = _parse_arguments(argv)
    model = arguments.descriptor or _current_descriptor(load_config_or_exit().library_root)
    upload = UPLOAD_DIRECTORY / model.name
    copy_atomically(model, upload)
    release = release_of(model, url=RELEASE_DOWNLOAD_URL.format(tag=arguments.tag, name=model.name))
    write_pretrained_release(release, PRETRAINED_RELEASE_PATH)
    print(f"Upload {upload} to the GitHub release {arguments.tag}, then commit {PRETRAINED_RELEASE_PATH}.")


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
