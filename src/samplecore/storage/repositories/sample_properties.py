from __future__ import annotations

from typing import Any, Protocol

import duckdb
from trackmod.core.samples.loop import Loop, LoopMode
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.sample_properties import (
    ITSampleProperties,
    SampleOccurrence,
    TrackerSampleProperties,
    Vibrato,
    XMSampleProperties,
)

_BASE_COLUMNS = ", ".join(
    (
        "sp.instrument_index",
        "sp.sample_slot",
        "sp.sample_hash",
        "sp.name",
        "sp.rate",
        "sp.volume",
        "sp.panning",
        "sp.loop_begin",
        "sp.loop_end",
        "sp.loop_mode",
    )
)

_SELECT_XM = f"""
    SELECT {_BASE_COLUMNS}, xm.relative_note, xm.finetune, m.hash
    FROM sample_properties sp
    JOIN xm_sample_properties xm USING (module_id, instrument_index, sample_slot)
    JOIN module m ON m.id = sp.module_id
    WHERE m.hash = ?
"""

_SELECT_IT = f"""
    SELECT {_BASE_COLUMNS},
        it.global_volume, it.sustain_begin, it.sustain_end, it.sustain_mode,
        it.filename, it.vibrato_speed, it.vibrato_depth, it.vibrato_rate, it.vibrato_waveform, m.hash
    FROM sample_properties sp
    JOIN it_sample_properties it USING (module_id, instrument_index, sample_slot)
    JOIN module m ON m.id = sp.module_id
    WHERE m.hash = ?
"""


class SamplePropertiesRepository(Protocol):
    """Persistence for tracker-specific occurrence properties, one row per (module, instrument, slot)."""

    def upsert(self, properties: TrackerSampleProperties) -> None: ...

    def list_for_module(self, module_hash: str) -> tuple[TrackerSampleProperties, ...]: ...


class DuckDBSamplePropertiesRepository:
    """A SamplePropertiesRepository backed by class-table inheritance: a shared base table plus one
    tracker-specific child table, joined back together on read by the ``tracker`` discriminator.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection

    def upsert(self, properties: TrackerSampleProperties) -> None:
        module_id = self._module_id(properties.occurrence.module_hash)
        self._insert_base(module_id, properties)
        match properties:
            case XMSampleProperties():
                self._insert_xm(module_id, properties)
            case ITSampleProperties():
                self._insert_it(module_id, properties)

    def list_for_module(self, module_hash: str) -> tuple[TrackerSampleProperties, ...]:
        xm_rows = self._connection.execute(_SELECT_XM, [module_hash]).fetchall()
        it_rows = self._connection.execute(_SELECT_IT, [module_hash]).fetchall()
        properties = [_row_to_xm_properties(row) for row in xm_rows] + [_row_to_it_properties(row) for row in it_rows]
        return tuple(
            sorted(properties, key=lambda item: (item.occurrence.instrument_index, item.occurrence.sample_slot))
        )

    def _module_id(self, module_hash: str) -> int:
        row = self._connection.execute("SELECT id FROM module WHERE hash = ?", [module_hash]).fetchone()
        if row is None:
            raise ValueError(f"no module ingested with hash {module_hash}")

        return int(row[0])

    def _insert_base(self, module_id: int, properties: TrackerSampleProperties) -> None:
        loop = properties.loop
        self._connection.execute(
            """
            INSERT INTO sample_properties
                (module_id, instrument_index, sample_slot, sample_hash, tracker, name, rate, volume, panning,
                 loop_begin, loop_end, loop_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (module_id, instrument_index, sample_slot) DO NOTHING
            """,
            [
                module_id,
                properties.occurrence.instrument_index,
                properties.occurrence.sample_slot,
                properties.sample_hash,
                properties.tracker.value,
                properties.name,
                properties.rate,
                properties.volume,
                properties.panning,
                loop.begin if loop is not None else None,
                loop.end if loop is not None else None,
                loop.mode.value if loop is not None else None,
            ],
        )

    def _insert_xm(self, module_id: int, properties: XMSampleProperties) -> None:
        self._connection.execute(
            """
            INSERT INTO xm_sample_properties (module_id, instrument_index, sample_slot, relative_note, finetune)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (module_id, instrument_index, sample_slot) DO NOTHING
            """,
            [
                module_id,
                properties.occurrence.instrument_index,
                properties.occurrence.sample_slot,
                properties.tuning.relative_note,
                properties.tuning.finetune,
            ],
        )

    def _insert_it(self, module_id: int, properties: ITSampleProperties) -> None:
        sustain_loop = properties.sustain_loop
        vibrato = properties.vibrato
        self._connection.execute(
            """
            INSERT INTO it_sample_properties (
                module_id, instrument_index, sample_slot, global_volume,
                sustain_begin, sustain_end, sustain_mode,
                filename, vibrato_speed, vibrato_depth, vibrato_rate, vibrato_waveform
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (module_id, instrument_index, sample_slot) DO NOTHING
            """,
            [
                module_id,
                properties.occurrence.instrument_index,
                properties.occurrence.sample_slot,
                properties.global_volume,
                sustain_loop.begin if sustain_loop is not None else None,
                sustain_loop.end if sustain_loop is not None else None,
                sustain_loop.mode.value if sustain_loop is not None else None,
                properties.filename,
                vibrato.speed if vibrato is not None else None,
                vibrato.depth if vibrato is not None else None,
                vibrato.rate if vibrato is not None else None,
                vibrato.waveform if vibrato is not None else None,
            ],
        )


def _loop_from_row(begin: int | None, end: int | None, mode: str | None) -> Loop | None:
    if begin is None:
        return None
    if end is None or mode is None:
        raise ValueError("a stored loop must have begin, end, and mode set together")

    return Loop(begin=begin, end=end, mode=LoopMode(mode))


def _vibrato_from_row(speed: int | None, depth: int | None, rate: int | None, waveform: int | None) -> Vibrato | None:
    if speed is None:
        return None
    if depth is None or rate is None or waveform is None:
        raise ValueError("a stored vibrato must have speed, depth, rate, and waveform set together")

    return Vibrato(speed=speed, depth=depth, rate=rate, waveform=waveform)


def _row_to_xm_properties(row: tuple[Any, ...]) -> XMSampleProperties:
    """Reconstruct an XMSampleProperties from a raw DuckDB row matching ``_SELECT_XM``'s column order."""
    (
        instrument_index,
        sample_slot,
        sample_hash,
        name,
        rate,
        volume,
        panning,
        loop_begin,
        loop_end,
        loop_mode,
        relative_note,
        finetune,
        module_hash,
    ) = row
    return XMSampleProperties(
        sample_hash=sample_hash,
        occurrence=SampleOccurrence(
            module_hash=module_hash, instrument_index=instrument_index, sample_slot=sample_slot
        ),
        name=name,
        rate=rate,
        volume=volume,
        panning=panning,
        loop=_loop_from_row(loop_begin, loop_end, loop_mode),
        tuning=Tuning(relative_note=relative_note, finetune=finetune),
    )


def _row_to_it_properties(row: tuple[Any, ...]) -> ITSampleProperties:
    """Reconstruct an ITSampleProperties from a raw DuckDB row matching ``_SELECT_IT``'s column order."""
    (
        instrument_index,
        sample_slot,
        sample_hash,
        name,
        rate,
        volume,
        panning,
        loop_begin,
        loop_end,
        loop_mode,
        global_volume,
        sustain_begin,
        sustain_end,
        sustain_mode,
        filename,
        vibrato_speed,
        vibrato_depth,
        vibrato_rate,
        vibrato_waveform,
        module_hash,
    ) = row
    return ITSampleProperties(
        sample_hash=sample_hash,
        occurrence=SampleOccurrence(
            module_hash=module_hash, instrument_index=instrument_index, sample_slot=sample_slot
        ),
        name=name,
        rate=rate,
        volume=volume,
        panning=panning,
        loop=_loop_from_row(loop_begin, loop_end, loop_mode),
        global_volume=global_volume,
        sustain_loop=_loop_from_row(sustain_begin, sustain_end, sustain_mode),
        filename=filename,
        vibrato=_vibrato_from_row(vibrato_speed, vibrato_depth, vibrato_rate, vibrato_waveform),
    )
