from __future__ import annotations

import base64
import hashlib
import zipfile
from pathlib import Path
from typing import Final

APP_EXTRA: Final[str] = "app"
METADATA_FILE: Final[str] = "METADATA"
RECORD_FILE: Final[str] = "RECORD"
REQUIRES_HEADER: Final[str] = "Requires-Dist: "
MARKER_SEPARATOR: Final[str] = ";"
OPTION_PREFIX: Final[str] = "-"


def write_pinned_wheel(wheel: Path, requirements: Path, output: Path) -> Path:
    """Write the wheel the packaged application embeds, whose app extra installs exactly the tested versions.

    The launcher installs an embedded wheel by its own metadata, so the locked versions travel inside
    it: every requirement becomes one more pinned dependency of the app extra.
    """
    output.mkdir(parents=True, exist_ok=True)
    target = output / wheel.name
    _write_pinned_wheel(wheel, target, _pins(requirements.read_text(encoding="utf-8")))
    return target


def _pins(requirements: str) -> list[str]:
    """Each requirement as a dependency of the app extra, its own environment marker kept beside the extra's."""
    pins: list[str] = []
    for line in requirements.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", OPTION_PREFIX)):
            continue
        specifier, _, marker = stripped.partition(MARKER_SEPARATOR)
        condition = f"({marker.strip()}) and extra == '{APP_EXTRA}'" if marker else f"extra == '{APP_EXTRA}'"
        pins.append(f"{specifier.strip()}; {condition}")
    return pins


def _write_pinned_wheel(source: Path, target: Path, pins: list[str]) -> None:
    """Copy every file of the wheel, the metadata with the pins added, and a record listing the new digests."""
    records: list[str] = []
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as pinned:
        record_name = next(name for name in original.namelist() if name.endswith(f".dist-info/{RECORD_FILE}"))
        for info in original.infolist():
            if info.filename == record_name:
                continue
            content = original.read(info.filename)
            if info.filename.endswith(f".dist-info/{METADATA_FILE}"):
                content = _pinned_metadata(content.decode("utf-8"), pins).encode("utf-8")
            pinned.writestr(info, content)
            records.append(f"{info.filename},{_record_digest(content)},{len(content)}")
        records.append(f"{record_name},,")
        pinned.writestr(record_name, "\n".join(records) + "\n")


def _pinned_metadata(metadata: str, pins: list[str]) -> str:
    """The metadata with the pins listed after the last dependency it already names."""
    lines = metadata.split("\n")
    last_requirement = max(index for index, line in enumerate(lines) if line.startswith(REQUIRES_HEADER))
    added = [f"{REQUIRES_HEADER}{pin}" for pin in pins]
    return "\n".join([*lines[: last_requirement + 1], *added, *lines[last_requirement + 1 :]])


def _record_digest(content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"
