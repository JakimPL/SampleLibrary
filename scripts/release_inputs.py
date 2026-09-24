from __future__ import annotations

import argparse
import sys
import tomllib
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path
from typing import Final

PROJECT_FILE: Final[Path] = Path("pyproject.toml")
TRACKMOD_PROJECT_FILE: Final[Path] = Path("trackmod") / "pyproject.toml"
TRACKMOD_PACKAGE: Final[str] = "trackmod"
PRETRAINED_DIRECTORY: Final[Path] = Path("src") / "sampledescriptor" / "pretrained"
PRETRAINED_FILES: Final[tuple[str, ...]] = ("descriptor.pt", "descriptor.json")
PYPI_RELEASE_URL: Final[str] = "https://pypi.org/pypi/{package}/{version}/json"
PYPI_TIMEOUT_SECONDS: Final[float] = 30.0
TAG_PREFIX: Final[str] = "v"


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check what a build of the application takes in, and write its version and trackmod as step outputs."
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
    """Write `version=` and `trackmod=` step outputs, the trackmod pinned to the submodule's version.

    The application installs trackmod from PyPI on its first start, so every build needs that
    version published. A release also needs the bundled descriptor, which new libraries build their
    cloud with; a build for trying out carries on with a warning.

    Raises:
        SystemExit: the tag names another version, PyPI lacks the submodule's trackmod version, or a
            release build finds no bundled descriptor.
    """
    arguments = _parse_arguments(argv)
    version = _project_version(PROJECT_FILE)
    if arguments.tag is not None and arguments.tag != f"{TAG_PREFIX}{version}":
        sys.exit(f"The tag {arguments.tag} doesn't match the project version {version}. Tag {TAG_PREFIX}{version}.")
    trackmod_version = _project_version(TRACKMOD_PROJECT_FILE)
    if not _published(TRACKMOD_PACKAGE, trackmod_version):
        sys.exit(f"trackmod {trackmod_version} isn't on PyPI yet. Publish it with `just publish-trackmod`.")
    missing = [name for name in PRETRAINED_FILES if not (PRETRAINED_DIRECTORY / name).is_file()]
    if missing:
        message = f"No bundled descriptor in {PRETRAINED_DIRECTORY.as_posix()}. Run `just bundle-descriptor` first."
        if arguments.tag is not None:
            sys.exit(message)
        print(f"::warning::{message} New libraries can build their catalog, but not their cloud.")
    with arguments.output.open("a", encoding="utf-8") as output:
        output.write(f"version={version}\n")
        output.write(f"trackmod={TRACKMOD_PACKAGE}=={trackmod_version}\n")


def _project_version(project_file: Path) -> str:
    with project_file.open("rb") as file:
        return str(tomllib.load(file)["project"]["version"])


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
