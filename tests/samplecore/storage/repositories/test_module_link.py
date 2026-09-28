from __future__ import annotations

import pytest
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from samplecore.models.module import Module
from samplecore.models.module_link import ModuleLink
from samplecore.storage.repositories.module_link import PostgresModuleLinkRepository

PAGE = "https://www.modules.pl/?id=module&mod=1"
ANOTHER_PAGE = "https://modarchive.org/index.php?request=view_by_moduleid&query=2"


def _link(module_hash: str, url: str = PAGE) -> ModuleLink:
    return ModuleLink(module_hash=module_hash, url=url)


def test_list_all_on_an_empty_table_returns_nothing(connection: Connection) -> None:
    assert PostgresModuleLinkRepository(connection).list_all() == ()


def test_a_link_round_trips_through_list_all(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleLinkRepository(connection)
    link = _link(stored_module.hash)

    repository.upsert_many((link,))

    assert repository.list_all() == (link,)


def test_upserting_the_same_module_again_replaces_its_link(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleLinkRepository(connection)
    repository.upsert_many((_link(stored_module.hash),))
    moved = _link(stored_module.hash, ANOTHER_PAGE)

    repository.upsert_many((moved,))

    assert repository.list_all() == (moved,)


def test_get_many_answers_the_modules_holding_a_link(
    connection: Connection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = PostgresModuleLinkRepository(connection)
    link = _link(stored_module.hash)
    repository.upsert_many((link,))

    assert repository.get_many([stored_module.hash, stored_module_b.hash]) == {stored_module.hash: link}


def test_empty_inputs_write_and_read_nothing(connection: Connection) -> None:
    repository = PostgresModuleLinkRepository(connection)

    repository.upsert_many(())

    assert repository.get_many([]) == {}
    assert repository.count() == 0


def test_count_counts_one_row_per_module(
    connection: Connection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = PostgresModuleLinkRepository(connection)

    repository.upsert_many((_link(stored_module.hash), _link(stored_module_b.hash, ANOTHER_PAGE)))

    assert repository.count() == 2


def test_one_write_naming_a_module_twice_is_refused(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleLinkRepository(connection)

    with pytest.raises(ValueError, match=stored_module.hash):
        repository.upsert_many((_link(stored_module.hash), _link(stored_module.hash, ANOTHER_PAGE)))

    assert repository.count() == 0


def test_a_link_needs_a_cataloged_module(connection: Connection, module_hash_a: str) -> None:
    with pytest.raises(IntegrityError):
        PostgresModuleLinkRepository(connection).upsert_many((_link(module_hash_a),))
