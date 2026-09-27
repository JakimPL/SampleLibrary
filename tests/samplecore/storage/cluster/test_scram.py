from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Final, cast

import pytest
from psycopg import Connection as PsycopgConnection
from sqlalchemy import Connection

from samplecore.storage.cluster.scram import DIGEST, SCRAM_MECHANISM, ScramKeys, prepared_password, scram_verifier

# RFC 7677, section 3: a SCRAM-SHA-256 exchange for the user "user" with the password "pencil".
RFC_PASSWORD: Final[str] = "pencil"
RFC_SALT: Final[str] = "W22ZaJ0SNY7soEsUEjb6gQ=="
RFC_ITERATIONS: Final[int] = 4096
RFC_AUTH_MESSAGE: Final[bytes] = (
    b"n=user,r=rOprNGfwEbeRWgbNEkqO,"
    b"r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096,"
    b"c=biws,r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0"
)
RFC_CLIENT_PROOF: Final[str] = "dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ="
RFC_SERVER_SIGNATURE: Final[str] = "6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4="


@dataclass(frozen=True)
class PreparationCase:
    password: str
    prepared: str


PREPARATION_CASES: Final[tuple[PreparationCase, ...]] = (
    PreparationCase(password="plain-ascii", prepared="plain-ascii"),
    PreparationCase(password="zażółć gęślą jaźń", prepared="zażółć gęślą jaźń"),
    PreparationCase(password="non breaking", prepared="non breaking"),
    PreparationCase(password="soft­hyphen", prepared="softhyphen"),
    PreparationCase(password="ligature ﬁ", prepared="ligature fi"),
    PreparationCase(password="control\u0085character", prepared="control\u0085character"),
)
CROSS_CHECKED_PASSWORDS: Final[tuple[str, ...]] = tuple(case.password for case in PREPARATION_CASES)


def test_the_keys_answer_the_exchange_rfc_7677_records() -> None:
    """The stored key proves the client's recorded proof, and the server key signs the recorded signature."""
    keys = ScramKeys.derive(RFC_PASSWORD, salt=base64.b64decode(RFC_SALT), iterations=RFC_ITERATIONS)

    client_signature = hmac.digest(keys.stored_key, RFC_AUTH_MESSAGE, DIGEST)
    client_key = bytes(
        proof ^ signature for proof, signature in zip(base64.b64decode(RFC_CLIENT_PROOF), client_signature, strict=True)
    )
    assert hashlib.new(DIGEST, client_key).digest() == keys.stored_key
    assert base64.b64encode(hmac.digest(keys.server_key, RFC_AUTH_MESSAGE, DIGEST)).decode() == RFC_SERVER_SIGNATURE


@pytest.mark.parametrize("case", PREPARATION_CASES, ids=lambda case: case.password)
def test_a_password_is_prepared_the_way_postgres_prepares_it(case: PreparationCase) -> None:
    assert prepared_password(case.password) == case.prepared


@pytest.mark.parametrize("password", CROSS_CHECKED_PASSWORDS)
def test_a_verifier_matches_the_one_libpq_derives_under_the_same_salt(connection: Connection, password: str) -> None:
    """libpq derives the verifier `psql`'s own password command sends, so agreeing with it is agreeing with Postgres."""
    driver = cast(PsycopgConnection, connection.connection.dbapi_connection)
    reference = driver.pgconn.encrypt_password(password.encode("utf-8"), b"any", b"scram-sha-256").decode("ascii")
    iterations, salt = reference.removeprefix(f"{SCRAM_MECHANISM}$").split("$")[0].split(":")

    derived = ScramKeys.derive(password, salt=base64.b64decode(salt), iterations=int(iterations))

    assert derived.verifier == reference


def test_each_verifier_takes_a_fresh_salt() -> None:
    assert scram_verifier(RFC_PASSWORD) != scram_verifier(RFC_PASSWORD)
