from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path
from typing import Final

from paths import PROJECT_FILE, TRACKMOD_PROJECT_FILE
from versions import project_version

from sampledescriptor.pretrained import (
    PretrainedDescriptorMissingError,
    PretrainedDownloadError,
    download_pretrained,
    pretrained_release,
)

TRACKMOD_PACKAGE: Final[str] = "trackmod"
PYPI_RELEASE_URL: Final[str] = "https://pypi.org/pypi/{package}/{version}/json"
PYPI_TIMEOUT_SECONDS: Final[float] = 30.0
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

    The application installs the submodule's trackmod version from PyPI on its first start, so every
    build needs that version published. A release also needs the published descriptor new libraries download to
    build their cloud; a build for trying out carries on with a warning.

    Raises:
        SystemExit: the tag names another version, PyPI lacks the submodule's trackmod version, or a
            release build finds no descriptor to download.
    """
    arguments = _parse_arguments(argv)
    version = project_version(PROJECT_FILE)
    if arguments.tag is not None and arguments.tag != f"{TAG_PREFIX}{version}":
        sys.exit(f"The tag {arguments.tag} doesn't match the project version {version}. Tag {TAG_PREFIX}{version}.")
    trackmod_version = project_version(TRACKMOD_PROJECT_FILE)
    if not _published(TRACKMOD_PACKAGE, trackmod_version):
        sys.exit(
            f"trackmod {trackmod_version} isn't on PyPI yet. Push TrackMod's v{trackmod_version} tag to publish it."
        )
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


def _published(package: str, version: str) -> bool:
    """Whether PyPI serves this version of the package.

    Raises:
        urllib.error.HTTPError: PyPI answers with an error other than a missing release.
    """
    url = PYPI_RELEASE_URL.format(package=package, version=version)
    try:
        with urllib.request.urlopen(url, timeout=PYPI_TIMEOUT_SECONDS):
            return True
    except urllib.error.HTTPError as error:
        if error.code == HTTPStatus.NOT_FOUND:
            return False
        raise


if __name__ == "__main__":
    main()
