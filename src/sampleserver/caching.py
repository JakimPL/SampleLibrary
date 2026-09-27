from __future__ import annotations

import hashlib
import secrets
from collections.abc import Hashable
from typing import Final

IMMUTABLE_CACHE_CONTROL: Final[str] = "public, max-age=31536000, immutable"
# A browser keeps an answer built over the whole catalog and asks each time whether it still stands.
REVALIDATED_CACHE_CONTROL: Final[str] = "no-cache"
# Each process names its answers apart from every other's, so an answer a browser kept from before a
# restart, such as the one following a new publication, is sent again rather than confirmed.
PROCESS_MARK: Final[str] = secrets.token_hex(8)


def entity_tag(revision: Hashable, *, encoding: str) -> str:
    """The validator of an answer built from ``revision`` of what it reads, in ``encoding``, by this process."""
    digest = hashlib.sha256(repr((PROCESS_MARK, revision, encoding)).encode("utf-8")).hexdigest()
    return f'"{digest}"'
