from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from typing import Final

from paths import (
    APP_REQUIREMENTS_FILE,
    FRONTEND_DIRECTORY,
    PACKAGE_BUILD_DIRECTORY,
    REPOSITORY_DIRECTORY,
    TRACKMOD_PROJECT_FILE,
)
from versions import project_version

APP_EXTRA: Final[str] = "app"
TRACKMOD_PACKAGE: Final[str] = "trackmod"
CPU_TORCH_INDEX: Final[str] = "https://download.pytorch.org/whl/cpu"
CUDA_BUILD: Final[re.Pattern[str]] = re.compile(r"^(torch==[^+\s;]+)\+cu\d+")
CUDA_ONLY_PACKAGES: Final[tuple[str, ...]] = ("nvidia-", "triton==")
LOCAL_SOURCE_PREFIXES: Final[tuple[str, ...]] = ("-e ", "./", "../")


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the samplelibrary wheel with the frontend inside, and the pinned requirements it installs."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Build what `just executable` wraps: the frontend, the wheel carrying it, and the app extra's locked versions.

    Raises:
        SystemExit: npm or uv is not installed.
    """
    _parse_arguments(argv)
    npm = _program("npm", "Install Node.js, which brings npm, first.")
    uv = _program("uv", "Install uv first: https://docs.astral.sh/uv/")
    subprocess.run([npm, "--prefix", str(FRONTEND_DIRECTORY), "run", "build"], check=True, cwd=REPOSITORY_DIRECTORY)
    subprocess.run(
        [uv, "build", "--wheel", "--clear", "--out-dir", str(PACKAGE_BUILD_DIRECTORY)],
        check=True,
        cwd=REPOSITORY_DIRECTORY,
    )
    count = _write_requirements(uv)
    print(f"Built the wheel and {count} pinned requirements in {PACKAGE_BUILD_DIRECTORY}.")


def _program(name: str, advice: str) -> str:
    """Where a program the build runs is installed, found on the PATH.

    Raises:
        SystemExit: the program is not on the PATH.
    """
    found = shutil.which(name)
    if found is None:
        sys.exit(f"{name} isn't installed. {advice}")
    return found


def _write_requirements(uv: str) -> int:
    """Write the locked versions of the app extra as the requirements a fresh installation reads.

    The lock pins the CUDA build of torch, which carries gigabytes of NVIDIA libraries; the packaged
    application takes the processor build of the same version from PyTorch's own index, which covers
    every machine, a card included. trackmod is a local path in a checkout, so an installation takes
    the submodule's version from PyPI.
    """
    exported = subprocess.run(
        [
            uv,
            "export",
            "--format",
            "requirements-txt",
            "--no-dev",
            "--no-hashes",
            "--no-emit-project",
            "--extra",
            APP_EXTRA,
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_DIRECTORY,
    ).stdout
    trackmod = f"{TRACKMOD_PACKAGE}=={project_version(TRACKMOD_PROJECT_FILE)}"
    requirements = [trackmod, *_processor_requirements(exported)]
    lines = [f"--extra-index-url {CPU_TORCH_INDEX}", *requirements]
    APP_REQUIREMENTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(requirements)


def _processor_requirements(exported: str) -> list[str]:
    """The exported pins with torch's CUDA build swapped for its processor build, and the CUDA-only packages left out."""
    kept: list[str] = []
    for line in exported.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(LOCAL_SOURCE_PREFIXES):
            continue
        if stripped.startswith(CUDA_ONLY_PACKAGES):
            continue
        kept.append(CUDA_BUILD.sub(r"\1+cpu", stripped))
    return kept


if __name__ == "__main__":
    main()
