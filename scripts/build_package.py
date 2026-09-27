from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from paths import (
    APP_REQUIREMENTS_FILE,
    FRONTEND_DIRECTORY,
    NVIDIA_REQUIREMENTS_FILE,
    PACKAGE_BUILD_DIRECTORY,
    REPOSITORY_DIRECTORY,
)
from torch_builds import CPU_TORCH_INDEX, CUDA_TORCH_INDEX

APP_EXTRA: Final[str] = "app"
CUDA_BUILD: Final[re.Pattern[str]] = re.compile(r"^(torch==[^+\s;]+)\+cu\d+")
CUDA_ONLY_PACKAGES: Final[tuple[str, ...]] = ("nvidia-", "triton==")


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the samplelibrary wheel with the frontend inside, and the pinned requirements it installs."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Build what `just executable` wraps: the frontend, the wheel carrying it, and each launcher's locked versions.

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
    processor_count, nvidia_count = _write_requirements(uv)
    print(
        f"Built the wheel and the pinned requirements in {PACKAGE_BUILD_DIRECTORY}: "
        f"{processor_count} for the processor launcher, {nvidia_count} for the NVIDIA one."
    )


def _program(name: str, advice: str) -> str:
    """Where a program the build runs is installed, found on the PATH.

    Raises:
        SystemExit: the program is not on the PATH.
    """
    found = shutil.which(name)
    if found is None:
        sys.exit(f"{name} isn't installed. {advice}")
    return found


def _write_requirements(uv: str) -> tuple[int, int]:
    """Write the locked versions of the app extra as the requirements a fresh installation reads.

    The lock pins the CUDA build of torch, which carries gigabytes of NVIDIA libraries. The processor
    launcher takes the processor build of the same version from PyTorch's own index, which runs on
    every machine; the NVIDIA launcher keeps the CUDA build and its libraries.
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
    locked = _locked_requirements(exported)
    processor = _processor_requirements(locked)
    nvidia = locked
    _write_requirement_file(APP_REQUIREMENTS_FILE, CPU_TORCH_INDEX, processor)
    _write_requirement_file(NVIDIA_REQUIREMENTS_FILE, CUDA_TORCH_INDEX, nvidia)
    return len(processor), len(nvidia)


def _locked_requirements(exported: str) -> list[str]:
    """The exported pins, leaving out the comments."""
    return [
        stripped
        for stripped in (line.strip() for line in exported.splitlines())
        if stripped and not stripped.startswith("#")
    ]


def _processor_requirements(locked: list[str]) -> list[str]:
    """The pins with torch's CUDA build swapped for its processor build, and the CUDA-only packages left out."""
    return [CUDA_BUILD.sub(r"\1+cpu", pin) for pin in locked if not pin.startswith(CUDA_ONLY_PACKAGES)]


def _write_requirement_file(path: Path, torch_index: str, requirements: list[str]) -> None:
    lines = [f"--extra-index-url {torch_index}", *requirements]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
