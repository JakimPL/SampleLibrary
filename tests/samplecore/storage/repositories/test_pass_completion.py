from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection

from samplecore.models.pass_completion import PassCompletion, PassKind
from samplecore.storage.repositories.pass_completion import PostgresPassCompletionRepository

FIRST_DIGEST = "1" * 64
SECOND_DIGEST = "2" * 64


def test_a_pass_never_finished_has_no_record(connection: Connection) -> None:
    passes = PostgresPassCompletionRepository(connection)

    assert passes.get(PassKind.NOTES) is None
    assert not passes.finished_over(PassKind.NOTES, FIRST_DIGEST)


def test_the_last_complete_pass_of_a_kind_replaces_the_one_before(connection: Connection) -> None:
    passes = PostgresPassCompletionRepository(connection)
    passes.record(PassCompletion(kind=PassKind.MODULES, digest=FIRST_DIGEST, completed_at=datetime.now(UTC)))
    passes.record(PassCompletion(kind=PassKind.MODULES, digest=SECOND_DIGEST, completed_at=datetime.now(UTC)))
    passes.record(PassCompletion(kind=PassKind.NOTES, digest=FIRST_DIGEST, completed_at=datetime.now(UTC)))

    assert passes.finished_over(PassKind.MODULES, SECOND_DIGEST)
    assert not passes.finished_over(PassKind.MODULES, FIRST_DIGEST)
    assert passes.finished_over(PassKind.NOTES, FIRST_DIGEST)


def test_a_forgotten_pass_of_one_kind_leaves_the_others(connection: Connection) -> None:
    passes = PostgresPassCompletionRepository(connection)
    passes.record(PassCompletion(kind=PassKind.MODULES, digest=FIRST_DIGEST, completed_at=datetime.now(UTC)))
    passes.record(PassCompletion(kind=PassKind.EQUIVALENCE, digest=FIRST_DIGEST, completed_at=datetime.now(UTC)))

    passes.forget(PassKind.MODULES)

    assert passes.get(PassKind.MODULES) is None
    assert passes.finished_over(PassKind.EQUIVALENCE, FIRST_DIGEST)
