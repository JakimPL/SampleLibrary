from __future__ import annotations

import secrets
from typing import Final

PASSWORD_BYTES: Final[int] = 24


def new_password() -> str:
    """A password this project chooses for a role or a server: 24 random bytes, URL-safe, 32 characters."""
    return secrets.token_urlsafe(PASSWORD_BYTES)
