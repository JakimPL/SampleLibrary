from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection, create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from samplecore.models.tracker import TrackerFormat
from samplecore.storage.curation import CURATION_SCHEMA
from samplecore.storage.database import (
    SCHEMA_LOCK_KEY,
    checkout_read_only,
    chunks,
    claim_named_lock,
    connect,
    connect_for_curation,
    create_pooled_engine,
    create_schema,
    module,
    named_lock_key,
)

EXPECTED_TABLES = frozenset(
    {
        "sample",
        "module",
        "sample_properties",
        "xm_sample_properties",
        "it_sample_properties",
        "sample_relation",
        "sample_label_suggestion",
    }
)


@pytest.fixture
def fresh_database_url(_database_url: str) -> Iterator[str]:
    """A brand-new, empty database on the shared test server, with no schema created yet.

    The shared ``connection`` fixture's database always already has its schema in place (only its
    rows are emptied between tests), so it cannot exercise ``connect()``'s own first-use schema
    creation -- this creates and drops a genuinely fresh database on the same server for exactly
    that. ``CREATE DATABASE``/``DROP DATABASE`` cannot run inside a transaction block, hence the
    ``AUTOCOMMIT`` isolation level.
    """
    admin_url = make_url(_database_url)
    database_name = f"fresh_{uuid.uuid4().hex}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as admin_connection:
        admin_connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        try:
            # str() on a URL renders its password as "***"; the yielded URL has to carry the real one.
            yield admin_url.set(database=database_name).render_as_string(hide_password=False)
        finally:
            admin_connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
    admin_engine.dispose()


def test_create_schema_creates_every_expected_table(connection: Connection) -> None:
    tables = set(inspect(connection).get_table_names())

    assert EXPECTED_TABLES <= tables


def test_create_schema_is_idempotent(connection: Connection) -> None:
    create_schema(connection)
    create_schema(connection)


def test_connect_creates_the_schema_in_a_fresh_database(fresh_database_url: str) -> None:
    connection = connect(fresh_database_url)
    try:
        tables = set(inspect(connection).get_table_names())
    finally:
        connection.close()

    assert EXPECTED_TABLES <= tables


def test_a_read_only_connection_never_creates_the_schema(fresh_database_url: str) -> None:
    connection = connect(fresh_database_url, read_only=True)
    try:
        tables = set(inspect(connection).get_table_names())
    finally:
        connection.close()

    assert tables == set()


def test_hand_labels_get_a_schema_of_their_own(connection: Connection) -> None:
    assert "sample_annotation" in set(inspect(connection).get_table_names(schema=CURATION_SCHEMA))


def test_a_curation_connection_prepares_labels_and_leaves_building_a_catalog_alone(
    fresh_database_url: str,
) -> None:
    """The served application owns the labels it records; the offline pipelines own the catalog."""
    connection = connect_for_curation(fresh_database_url)
    try:
        catalog_tables = set(inspect(connection).get_table_names())
        curation_tables = set(inspect(connection).get_table_names(schema=CURATION_SCHEMA))
    finally:
        connection.close()

    assert catalog_tables == set()
    assert curation_tables == {"sample_annotation", "tag_rank"}


def test_a_curation_connection_waits_for_the_schema_claim(connection: Connection, _database_url: str) -> None:
    """Workers starting together each prepare the curation schema, one after another.

    The other run asks with a short lock timeout, so the test reports the wait instead of blocking on it.
    """
    impatient_url = make_url(_database_url).update_query_dict({"options": "-c lock_timeout=200"})
    connection.execute(select(func.pg_advisory_xact_lock(SCHEMA_LOCK_KEY)))
    try:
        with pytest.raises(DBAPIError, match="lock timeout"):
            connect_for_curation(impatient_url.render_as_string(hide_password=False))
    finally:
        connection.rollback()


def test_creating_the_schema_holds_a_claim_no_other_run_can_take(connection: Connection, _database_url: str) -> None:
    """Two runs opening one fresh catalog would otherwise both try to create the same table.

    The second connection stands for that other run, asking for the claim rather than waiting on
    it, so the test reports the state instead of blocking on it.
    """
    with connect(_database_url) as other_run:
        create_schema(connection)
        while_creating = other_run.execute(select(func.pg_try_advisory_xact_lock(SCHEMA_LOCK_KEY))).scalar_one()
        connection.commit()
        once_created = other_run.execute(select(func.pg_try_advisory_xact_lock(SCHEMA_LOCK_KEY))).scalar_one()

    assert not while_creating
    assert once_created


def test_a_pooled_checkout_refuses_a_write_on_every_use(connection: Connection, _database_url: str) -> None:
    """The read-only rule travels with each checkout, so a connection back from the pool is as safe as a fresh one."""
    engine = create_pooled_engine(_database_url, pool_size=1)
    try:
        for _ in range(2):
            checked_out = checkout_read_only(engine)
            try:
                assert checked_out.execute(text("SELECT 1")).scalar_one() == 1
                with pytest.raises(DBAPIError, match="read-only"):
                    checked_out.execute(text("INSERT INTO sample_playback_rate (sample_hash, rate) VALUES ('a', 1)"))
            finally:
                checked_out.close()
    finally:
        engine.dispose()


def _module_row(filename: str) -> dict[str, object]:
    return {
        "hash": "a" * 64,
        "filename": filename,
        "tracker": TrackerFormat.XM.value,
        "title": "",
        "channel_count": 1,
        "pattern_count": 1,
        "instrument_count": 1,
        "sample_count": 1,
        "file_size": 1,
        "ingested_at": datetime.now(UTC),
    }


@pytest.mark.parametrize("filename", ["song.xm", "100% pure.it"], ids=("plain", "a percent sign"))
def test_a_module_filename_naming_a_file_is_stored(connection: Connection, filename: str) -> None:
    connection.execute(module.insert().values(_module_row(filename)))

    assert connection.execute(select(module.c.filename)).scalar_one() == filename


@pytest.mark.parametrize("filename", ["folder/song.xm", "folder\\song.xm"], ids=("a slash", "a backslash"))
def test_a_module_filename_carrying_a_directory_is_refused(connection: Connection, filename: str) -> None:
    with pytest.raises(IntegrityError, match="module_filename_check"):
        connection.execute(module.insert().values(_module_row(filename)))


@pytest.mark.parametrize(
    ("size", "expected"), [(2, [[1, 2], [3, 4], [5]]), (5, [[1, 2, 3, 4, 5]]), (9, [[1, 2, 3, 4, 5]])]
)
def test_chunks_cover_every_item_in_order(size: int, expected: list[list[int]]) -> None:
    assert [list(chunk) for chunk in chunks([1, 2, 3, 4, 5], size)] == expected


def test_a_writable_checkout_between_read_only_ones_writes_and_leaves_the_next_read_only(
    connection: Connection, _database_url: str
) -> None:
    """The curation routes write through the same pool the reading routes check read-only connections out of."""
    engine = create_pooled_engine(_database_url, pool_size=1)
    insert_rate = text("INSERT INTO curation.tag_rank (path, rank) VALUES ('KICK', 0)")
    try:
        checkout_read_only(engine).close()
        with engine.connect() as writable:
            writable.execute(insert_rate)
            writable.commit()
        checked_out = checkout_read_only(engine)
        try:
            with pytest.raises(DBAPIError, match="read-only"):
                checked_out.execute(text("INSERT INTO curation.tag_rank (path, rank) VALUES ('SNARE', 1)"))
        finally:
            checked_out.close()
    finally:
        engine.dispose()


def test_one_lock_name_stands_for_one_key_in_the_signed_64_bit_range() -> None:
    names = ("samplelibrary-a-teacher", "samplelibrary-a-descriptor", "samplelibrary-b-teacher")
    keys = [named_lock_key(name) for name in names]

    assert keys == [named_lock_key(name) for name in names]
    assert len(set(keys)) == len(names)
    assert all(-(2**63) <= key < 2**63 for key in keys)


def test_a_named_lock_is_free_again_once_the_connection_holding_it_closes(
    connection: Connection, _database_url: str
) -> None:
    holder = connect(_database_url, read_only=True)
    assert claim_named_lock(holder, "samplelibrary-held-step")

    assert not claim_named_lock(connection, "samplelibrary-held-step")
    holder.close()
    assert claim_named_lock(connection, "samplelibrary-held-step")
    connection.execute(select(func.pg_advisory_unlock(named_lock_key("samplelibrary-held-step"))))
