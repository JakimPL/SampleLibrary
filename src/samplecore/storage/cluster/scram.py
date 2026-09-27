from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import stringprep
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

SCRAM_MECHANISM: Final[str] = "SCRAM-SHA-256"
SCRAM_ITERATIONS: Final[int] = 4096
SALT_BYTES: Final[int] = 16
DIGEST: Final[str] = "sha256"
CLIENT_KEY_LABEL: Final[bytes] = b"Client Key"
SERVER_KEY_LABEL: Final[bytes] = b"Server Key"

# The characters RFC 4013 prohibits in a prepared string, as the stringprep tables name them.
_PROHIBITED: Final[tuple[Callable[[str], bool], ...]] = (
    stringprep.in_table_c12,
    stringprep.in_table_c21_c22,
    stringprep.in_table_c3,
    stringprep.in_table_c4,
    stringprep.in_table_c5,
    stringprep.in_table_c6,
    stringprep.in_table_c7,
    stringprep.in_table_c8,
    stringprep.in_table_c9,
    stringprep.in_table_a1,
)


@dataclass(frozen=True)
class ScramKeys:
    """The two keys a server keeps for a SCRAM-SHA-256 login, derived from a password and a salt."""

    salt: bytes
    iterations: int
    stored_key: bytes
    server_key: bytes

    @classmethod
    def derive(cls, password: str, *, salt: bytes, iterations: int) -> ScramKeys:
        """Derive the keys RFC 5802 names from ``password``, prepared the way Postgres prepares it."""
        salted = hashlib.pbkdf2_hmac(DIGEST, prepared_password(password).encode("utf-8"), salt, iterations)
        client_key = hmac.digest(salted, CLIENT_KEY_LABEL, DIGEST)
        return cls(
            salt=salt,
            iterations=iterations,
            stored_key=hashlib.new(DIGEST, client_key).digest(),
            server_key=hmac.digest(salted, SERVER_KEY_LABEL, DIGEST),
        )

    @property
    def verifier(self) -> str:
        """The keys in the form Postgres stores a password in, and takes as a role's password as it is."""
        return (
            f"{SCRAM_MECHANISM}${self.iterations}:{_encoded(self.salt)}"
            f"${_encoded(self.stored_key)}:{_encoded(self.server_key)}"
        )


def scram_verifier(password: str) -> str:
    """The SCRAM-SHA-256 verifier of ``password`` under a fresh salt.

    A role given its password this way logs in with the password itself, while the statement that
    sets it, and any server log recording that statement, carries only what the server keeps.
    """
    return ScramKeys.derive(password, salt=secrets.token_bytes(SALT_BYTES), iterations=SCRAM_ITERATIONS).verifier


def prepared_password(password: str) -> str:
    """The password as Postgres hashes it: SASLprep applied, and the password kept as typed where SASLprep refuses it.

    An ASCII password is its own preparation. Any other is mapped (non-ASCII spaces to a space, the
    characters RFC 3454 maps to nothing dropped) and normalized to NFKC, then checked for prohibited
    and unassigned characters and for mixed directions, any of which leaves the password as typed.
    """
    if password.isascii():
        return password
    mapped = "".join(
        " " if stringprep.in_table_c12(character) else character
        for character in password
        if not stringprep.in_table_b1(character)
    )
    normalized = unicodedata.normalize("NFKC", mapped)
    if not normalized or any(test(character) for character in normalized for test in _PROHIBITED):
        return password
    if not _directions_agree(normalized):
        return password
    return normalized


def _directions_agree(prepared: str) -> bool:
    """Whether a prepared string meets RFC 3454's rule for text written right to left."""
    right_to_left = [stringprep.in_table_d1(character) for character in prepared]
    if not any(right_to_left):
        return True
    left_to_right = any(stringprep.in_table_d2(character) for character in prepared)
    return not left_to_right and right_to_left[0] and right_to_left[-1]


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")
