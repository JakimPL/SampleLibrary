from __future__ import annotations

import base64
import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

APP_EXTRA: Final[str] = "app"
METADATA_FILE: Final[str] = "METADATA"
RECORD_FILE: Final[str] = "RECORD"
REQUIRES_HEADER: Final[str] = "Requires-Dist: "
VERSION_HEADER: Final[str] = "Version: "
DIST_INFO_SUFFIX: Final[str] = ".dist-info"
MARKER_SEPARATOR: Final[str] = ";"
OPTION_PREFIX: Final[str] = "-"


def write_pinned_wheel(wheel: Path, requirements: Path, output: Path, *, local_version: str | None) -> Path:
    """Write the wheel the packaged application embeds, whose app extra installs exactly the tested versions.

    The launcher installs an embedded wheel by its own metadata, so the locked versions travel inside
    it: every requirement becomes one more pinned dependency of the app extra. A ``local_version``
    label joins the wheel's version, its name and its metadata folder, which gives the installation
    of a launcher built from it a folder apart from the others'.
    """
    output.mkdir(parents=True, exist_ok=True)
    name, version, rest = wheel.name.split("-", 2)
    labeled = f"{version}+{local_version}" if local_version is not None else version
    target = output / f"{name}-{labeled}-{rest}"
    renaming = _Renaming(before=f"{name}-{version}{DIST_INFO_SUFFIX}/", after=f"{name}-{labeled}{DIST_INFO_SUFFIX}/")
    _write_pinned_wheel(wheel, target, _pins(requirements.read_text(encoding="utf-8")), renaming, version=labeled)
    return target


@dataclass(frozen=True)
class _Renaming:
    """The metadata folder's name before and after the wheel's version takes its local label."""

    before: str
    after: str

    def apply(self, file_name: str) -> str:
        return self.after + file_name.removeprefix(self.before) if file_name.startswith(self.before) else file_name


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


def _write_pinned_wheel(source: Path, target: Path, pins: list[str], renaming: _Renaming, *, version: str) -> None:
    """Copy every file of the wheel, the metadata with the pins and the version, and a record listing the new digests."""
    records: list[str] = []
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as pinned:
        record_name = next(name for name in original.namelist() if name.endswith(f"{DIST_INFO_SUFFIX}/{RECORD_FILE}"))
        for info in original.infolist():
            if info.filename == record_name:
                continue
            content = original.read(info.filename)
            if info.filename.endswith(f"{DIST_INFO_SUFFIX}/{METADATA_FILE}"):
                content = _pinned_metadata(content.decode("utf-8"), pins, version=version).encode("utf-8")
            info.filename = renaming.apply(info.filename)
            pinned.writestr(info, content)
            records.append(f"{info.filename},{_record_digest(content)},{len(content)}")
        renamed_record = renaming.apply(record_name)
        records.append(f"{renamed_record},,")
        pinned.writestr(renamed_record, "\n".join(records) + "\n")


def _pinned_metadata(metadata: str, pins: list[str], *, version: str) -> str:
    """The metadata at ``version``, with the pins listed after the last dependency it already names."""
    lines = [f"{VERSION_HEADER}{version}" if line.startswith(VERSION_HEADER) else line for line in metadata.split("\n")]
    last_requirement = max(index for index, line in enumerate(lines) if line.startswith(REQUIRES_HEADER))
    added = [f"{REQUIRES_HEADER}{pin}" for pin in pins]
    return "\n".join([*lines[: last_requirement + 1], *added, *lines[last_requirement + 1 :]])


def _record_digest(content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"
