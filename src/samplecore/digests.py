from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

DigestValue = str | int | float | bool | None


def digest_of_rows(rows: Iterable[Sequence[DigestValue]]) -> str:
    """One SHA-256 over rows taken in the order given, each written as a compact JSON array on a line of its own.

    Every value keeps its type and every row its boundaries, so rows whose values would run together
    as plain text -- ``("a,b",)`` beside ``("a", "b")`` -- digest apart, and a caller orders its rows
    before handing them over, so two readings of the same rows agree.
    """
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def stat_digest(root: Path, paths: Sequence[Path]) -> str:
    """One digest over the files under ``root``: each path relative to it, its size and its write time, in path order.

    A file added, removed, renamed, resized or written again moves the digest, and a collection
    listed under another root at the same relative places keeps it. A path that is gone by the time
    it is read digests as absent, so a file vanishing between a listing and this call moves the
    digest as well.
    """
    rows: list[tuple[str, int | None, int | None]] = []
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        try:
            status = path.stat()
        except OSError:
            rows.append((relative, None, None))
            continue
        rows.append((relative, status.st_size, status.st_mtime_ns))
    return digest_of_rows(rows)
