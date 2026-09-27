from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Final

from paths import PROJECT_FILE
from versions import project_version

from sampledescriptor.pretrained import (
    PretrainedDescriptorMissingError,
    PretrainedDownloadError,
    download_pretrained,
    pretrained_release,
)

DOWNLOADED_DESCRIPTOR_NAME: Final[str] = "descriptor.pt"
TAG_PREFIX: Final[str] = "v"


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check what a build of the application takes in, and write its version as a step output."
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="The file GitHub reads step outputs from, which `$GITHUB_OUTPUT` names.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="The tag a release build runs for, which must name the project's version, such as v0.1.0.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Check a build's inputs and write its `version=` step output.

    A release needs the published descriptor new libraries download to build their cloud; a build
    for trying out carries on with a warning.

    Raises:
        SystemExit: the tag names another version, or a release build finds no descriptor to download.
    """
    arguments = _parse_arguments(argv)
    version = project_version(PROJECT_FILE)
    if arguments.tag is not None and arguments.tag != f"{TAG_PREFIX}{version}":
        sys.exit(f"The tag {arguments.tag} doesn't match the project version {version}. Tag {TAG_PREFIX}{version}.")
    problem = _pretrained_problem()
    if problem is not None:
        if arguments.tag is not None:
            sys.exit(problem)
        print(f"::warning::{problem} New libraries train a descriptor of their own.")
    with arguments.output.open("a", encoding="utf-8") as output:
        output.write(f"version={version}\n")


def _pretrained_problem() -> str | None:
    """What keeps new libraries from getting the published descriptor, or None when it downloads intact.

    The check downloads it the way a library's build does, verifying its bytes against the release.
    """
    try:
        release = pretrained_release()
    except PretrainedDescriptorMissingError as error:
        return str(error)
    with tempfile.TemporaryDirectory() as directory:
        try:
            download_pretrained(release, Path(directory) / DOWNLOADED_DESCRIPTOR_NAME)
        except PretrainedDownloadError as error:
            return str(error)
    return None


if __name__ == "__main__":
    main()
