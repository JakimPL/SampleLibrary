from __future__ import annotations

import pytest

from samplecore.storage.cluster.quoting import UnsafeValueError, identifier, literal


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("samplelibrary", '"samplelibrary"'),
        ("samplelibrary_dev", '"samplelibrary_dev"'),
        ('weird"name', '"weird""name"'),
        ("Mixed Case", '"Mixed Case"'),
        ("drop database postgres; --", '"drop database postgres; --"'),
    ],
)
def test_an_identifier_stands_for_itself_however_it_is_spelled(value: str, expected: str) -> None:
    assert identifier(value).as_string(None) == expected


@pytest.mark.parametrize("value", ["", "na\x00me"])
def test_a_name_quoting_cannot_carry_is_rejected(value: str) -> None:
    """A NUL cuts a name short at the driver, and an empty name reaches Postgres as a syntax error."""
    with pytest.raises(UnsafeValueError):
        identifier(value)


@pytest.mark.parametrize("value", ["samplelibrary", "pa'ss", "back\\slash", "'; DROP DATABASE postgres; --"])
def test_a_literal_stands_for_itself_however_it_is_spelled(value: str) -> None:
    """Whatever the value carries, what comes back is one quoted literal and nothing more.

    A value holding a backslash is emitted in Postgres's ``E'...'`` form, which the driver leads
    with a space, so the token is read out of the composed text rather than off its first character.
    """
    composed = literal(value).as_string(None).strip()

    assert composed.startswith(("'", "E'"))
    assert composed.endswith("'")


def test_a_literal_holding_a_nul_is_rejected() -> None:
    with pytest.raises(UnsafeValueError):
        literal("pass\x00word")


def test_a_rejected_literal_is_reported_without_repeating_it() -> None:
    """A password reaching a log or a console is the thing this message must avoid."""
    with pytest.raises(UnsafeValueError) as error_info:
        literal("hunter2\x00")

    assert "hunter2" not in str(error_info.value)
