from __future__ import annotations

import secrets
from typing import Final

PASSWORD_BYTES: Final[int] = 24
# The shortest password a role serving the internet logs in with: a generated one, 32 characters,
# clears it, and one a person picked to remember rarely does.
MINIMUM_SERVICE_PASSWORD_LENGTH: Final[int] = 24


def new_password() -> str:
    """A password this project chooses for a role or a server: 24 random bytes, URL-safe, 32 characters."""
    return secrets.token_urlsafe(PASSWORD_BYTES)
