from __future__ import annotations

from sqlalchemy import Connection
from trackmod.core.instruments.behaviour import DuplicateAction, DuplicateCheck, NewNoteAction

from samplecore.models.module import Module
from samplecore.models.module_instrument import ModuleInstrument
from samplecore.storage.repositories.module_instrument import PostgresModuleInstrumentRepository


def _instrument(module: Module, *, instrument_index: int = 0, name: str = "bell") -> ModuleInstrument:
    return ModuleInstrument(
        module_id=module.id,
        instrument_index=instrument_index,
        name=name,
        fadeout=256,
        global_volume=128,
        panning=None,
        new_note_action=NewNoteAction.FADE,
        duplicate_check=DuplicateCheck.NOTE,
        duplicate_action=DuplicateAction.NOTE_OFF,
    )


def test_a_stored_instrument_round_trips_through_list_for_module(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleInstrumentRepository(connection)
    instrument = _instrument(stored_module)

    repository.insert_many([instrument])

    assert repository.list_for_module(stored_module.id) == (instrument,)


def test_list_for_module_orders_instruments_by_their_slot(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleInstrumentRepository(connection)
    second = _instrument(stored_module, instrument_index=1, name="pad")
    first = _instrument(stored_module, instrument_index=0, name="bell")

    repository.insert_many([second, first])

    assert repository.list_for_module(stored_module.id) == (first, second)


def test_inserting_no_instruments_leaves_the_table_untouched(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleInstrumentRepository(connection)

    repository.insert_many([])

    assert repository.list_for_module(stored_module.id) == ()


def test_names_by_module_groups_every_named_slot_under_its_module(
    connection: Connection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = PostgresModuleInstrumentRepository(connection)
    repository.insert_many(
        [
            _instrument(stored_module, instrument_index=0, name="bell"),
            _instrument(stored_module, instrument_index=1, name="pad"),
            _instrument(stored_module_b, instrument_index=0, name="kick"),
        ]
    )

    names = repository.names_by_module([stored_module.id, stored_module_b.id])

    assert names == {stored_module.id: ("bell", "pad"), stored_module_b.id: ("kick",)}


def test_names_by_module_reports_only_slots_carrying_a_name(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleInstrumentRepository(connection)
    repository.insert_many(
        [
            _instrument(stored_module, instrument_index=0, name=""),
            _instrument(stored_module, instrument_index=1, name="pad"),
        ]
    )

    assert repository.names_by_module([stored_module.id]) == {stored_module.id: ("pad",)}


def test_names_by_module_with_no_modules_returns_nothing(connection: Connection) -> None:
    assert PostgresModuleInstrumentRepository(connection).names_by_module([]) == {}


def test_delete_for_module_removes_only_that_module_s_instruments(
    connection: Connection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = PostgresModuleInstrumentRepository(connection)
    kept = _instrument(stored_module_b)
    repository.insert_many([_instrument(stored_module), kept])

    repository.delete_for_module(stored_module.id)

    assert repository.list_for_module(stored_module.id) == ()
    assert repository.list_for_module(stored_module_b.id) == (kept,)
