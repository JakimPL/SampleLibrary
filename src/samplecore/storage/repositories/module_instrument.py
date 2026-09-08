from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, select
from trackmod.core.instruments.behavior import DuplicateAction, DuplicateCheck, NewNoteAction

from samplecore.models.module_instrument import ModuleInstrument
from samplecore.storage.database import bulk_insert, module_instrument

_COLUMN_NAMES: Final[tuple[str, ...]] = (
    "module_id",
    "instrument_index",
    "name",
    "fadeout",
    "global_volume",
    "panning",
    "new_note_action",
    "duplicate_check",
    "duplicate_action",
)


class ModuleInstrumentRepository(Protocol):
    """Persistence for a module's instrument slots, as its voice table numbers them."""

    def insert_many(self, instruments: Sequence[ModuleInstrument]) -> None: ...

    def list_for_module(self, module_id: int) -> tuple[ModuleInstrument, ...]: ...

    def names_by_module(self, module_ids: Sequence[int]) -> dict[int, tuple[str, ...]]: ...

    def delete_for_module(self, module_id: int) -> None: ...


class PostgresModuleInstrumentRepository:
    """A ModuleInstrumentRepository backed by the catalog's ``module_instrument`` table.

    A module's slots are written once, inside the transaction that reads its patterns, so
    ``insert_many`` states no conflict resolution; re-reading a module clears its rows through
    ``delete_for_module`` first.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert_many(self, instruments: Sequence[ModuleInstrument]) -> None:
        if not instruments:
            return

        bulk_insert(
            self._connection,
            module_instrument,
            _COLUMN_NAMES,
            (
                (
                    instrument.module_id,
                    instrument.instrument_index,
                    instrument.name,
                    instrument.fadeout,
                    instrument.global_volume,
                    instrument.panning,
                    instrument.new_note_action.value,
                    instrument.duplicate_check.value,
                    instrument.duplicate_action.value,
                )
                for instrument in instruments
            ),
        )

    def list_for_module(self, module_id: int) -> tuple[ModuleInstrument, ...]:
        statement = (
            select(module_instrument)
            .where(module_instrument.c.module_id == module_id)
            .order_by(module_instrument.c.instrument_index)
        )
        rows = self._connection.execute(statement).fetchall()
        return tuple(_row_to_module_instrument(row) for row in rows)

    def names_by_module(self, module_ids: Sequence[int]) -> dict[int, tuple[str, ...]]:
        """Every non-empty instrument name each given module carries, keyed by module id.

        An instrument is named apart from the waveforms its keys reach, which makes these names a
        source of description a sample's own name leaves out.
        """
        if not module_ids:
            return {}

        statement = (
            select(module_instrument.c.module_id, module_instrument.c.name)
            .where(module_instrument.c.module_id.in_(module_ids))
            .where(module_instrument.c.name != "")
            .order_by(module_instrument.c.module_id, module_instrument.c.instrument_index)
        )
        names_by_module: dict[int, list[str]] = {}
        for row in self._connection.execute(statement).fetchall():
            names_by_module.setdefault(row.module_id, []).append(row.name)

        return {module_id: tuple(names) for module_id, names in names_by_module.items()}

    def delete_for_module(self, module_id: int) -> None:
        self._connection.execute(module_instrument.delete().where(module_instrument.c.module_id == module_id))


def _row_to_module_instrument(row: Row[Any]) -> ModuleInstrument:
    """Reconstruct a ModuleInstrument from a Core row, addressed by its own column names."""
    return ModuleInstrument(
        module_id=row.module_id,
        instrument_index=row.instrument_index,
        name=row.name,
        fadeout=row.fadeout,
        global_volume=row.global_volume,
        panning=row.panning,
        new_note_action=NewNoteAction(row.new_note_action),
        duplicate_check=DuplicateCheck(row.duplicate_check),
        duplicate_action=DuplicateAction(row.duplicate_action),
    )
