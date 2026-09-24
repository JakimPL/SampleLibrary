from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Final

APP_EXTRA: Final[str] = "app"
CPU_TORCH_INDEX: Final[str] = "https://download.pytorch.org/whl/cpu"
CUDA_BUILD: Final[re.Pattern[str]] = re.compile(r"^(torch==[^+\s;]+)\+cu\d+")
CUDA_ONLY_PACKAGES: Final[tuple[str, ...]] = ("nvidia-", "triton==")
LOCAL_SOURCE_PREFIXES: Final[tuple[str, ...]] = ("-e ", "./", "../")


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write the pinned requirements the packaged application installs, with torch built for the processor."
    )
    parser.add_argument("--output", type=Path, required=True, help="The requirements file to write.")
    parser.add_argument(
        "--trackmod",
        type=str,
        required=True,
        help="Where the installer takes trackmod from: a pinned version, a wheel URL or a wheel path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Export the locked versions of the app extra as the requirements a fresh installation reads.

    The lock pins the CUDA build of torch, which carries gigabytes of NVIDIA libraries; the packaged
    application takes the processor build of the same version from PyTorch's own index, which covers
    every machine, a card included. trackmod is a local path in a checkout, so the caller says where
    an installation finds it.
    """
    arguments = _parse_arguments(argv)
    exported = subprocess.run(
        [
            "uv",
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
    ).stdout
    lines = [f"--extra-index-url {CPU_TORCH_INDEX}", arguments.trackmod, *_processor_requirements(exported)]
    arguments.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines) - 1} requirements to {arguments.output}.")


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
