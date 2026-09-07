from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import ColumnElement, Connection, Row, select
from sqlalchemy.dialects.postgresql import insert
from trackmod.core.samples.loop import Loop, LoopMode
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.sample_properties import (
    ITSampleProperties,
    MODSampleProperties,
    S3MSampleProperties,
    SampleOccurrence,
    TrackerSampleProperties,
    Vibrato,
    XMSampleProperties,
)
from samplecore.storage.database import (
    it_sample_properties,
    module,
    s3m_sample_properties,
    sample_properties,
    xm_sample_properties,
)

_BASE_COLUMNS = (
    sample_properties.c.instrument_index,
    sample_properties.c.sample_slot,
    sample_properties.c.sample_hash,
    sample_properties.c.name,
    sample_properties.c.rate,
    sample_properties.c.volume,
    sample_properties.c.panning,
    sample_properties.c.loop_begin,
    sample_properties.c.loop_end,
    sample_properties.c.loop_mode,
)

_XM_JOIN = sample_properties.join(
    xm_sample_properties,
    (xm_sample_properties.c.module_id == sample_properties.c.module_id)
    & (xm_sample_properties.c.instrument_index == sample_properties.c.instrument_index)
    & (xm_sample_properties.c.sample_slot == sample_properties.c.sample_slot),
).join(module, module.c.id == sample_properties.c.module_id)

_IT_JOIN = sample_properties.join(
    it_sample_properties,
    (it_sample_properties.c.module_id == sample_properties.c.module_id)
    & (it_sample_properties.c.instrument_index == sample_properties.c.instrument_index)
    & (it_sample_properties.c.sample_slot == sample_properties.c.sample_slot),
).join(module, module.c.id == sample_properties.c.module_id)

# MOD carries nothing beyond the shared base (see MODSampleProperties's own docstring), so its rows
# are read straight off sample_properties -- no child table to join.
_MOD_JOIN = sample_properties.join(module, module.c.id == sample_properties.c.module_id)

_S3M_JOIN = sample_properties.join(
    s3m_sample_properties,
    (s3m_sample_properties.c.module_id == sample_properties.c.module_id)
    & (s3m_sample_properties.c.instrument_index == sample_properties.c.instrument_index)
    & (s3m_sample_properties.c.sample_slot == sample_properties.c.sample_slot),
).join(module, module.c.id == sample_properties.c.module_id)


class SamplePropertiesRepository(Protocol):
    """Persistence for tracker-specific occurrence properties, one row per (module, instrument, slot)."""

    def upsert(self, properties: TrackerSampleProperties) -> None: ...

    def list_for_module(self, module_hash: str) -> tuple[TrackerSampleProperties, ...]: ...

    def list_for_sample(self, sample_hash: str) -> tuple[TrackerSampleProperties, ...]: ...


class PostgresSamplePropertiesRepository:
    """A SamplePropertiesRepository backed by class-table inheritance: a shared base table plus one
    tracker-specific child table, joined back together on read by the ``tracker`` discriminator.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert(self, properties: TrackerSampleProperties) -> None:
        module_id = self._module_id(properties.occurrence.module_hash)
        self._insert_base(module_id, properties)
        match properties:
            case XMSampleProperties():
                self._insert_xm(module_id, properties)
            case ITSampleProperties():
                self._insert_it(module_id, properties)
            case MODSampleProperties():
                pass
            case S3MSampleProperties():
                self._insert_s3m(module_id, properties)

    def list_for_module(self, module_hash: str) -> tuple[TrackerSampleProperties, ...]:
        return self._list_by(module.c.hash == module_hash)

    def list_for_sample(self, sample_hash: str) -> tuple[TrackerSampleProperties, ...]:
        return self._list_by(sample_properties.c.sample_hash == sample_hash)

    def _list_by(self, condition: ColumnElement[bool]) -> tuple[TrackerSampleProperties, ...]:
        xm_statement = (
            select(*_BASE_COLUMNS, xm_sample_properties.c.relative_note, xm_sample_properties.c.finetune, module.c.hash)
            .select_from(_XM_JOIN)
            .where(condition)
        )
        it_statement = (
            select(
                *_BASE_COLUMNS,
                it_sample_properties.c.global_volume,
                it_sample_properties.c.sustain_begin,
                it_sample_properties.c.sustain_end,
                it_sample_properties.c.sustain_mode,
                it_sample_properties.c.filename,
                it_sample_properties.c.vibrato_speed,
                it_sample_properties.c.vibrato_depth,
                it_sample_properties.c.vibrato_rate,
                it_sample_properties.c.vibrato_waveform,
                module.c.hash,
            )
            .select_from(_IT_JOIN)
            .where(condition)
        )
        mod_statement = (
            select(*_BASE_COLUMNS, module.c.hash)
            .select_from(_MOD_JOIN)
            .where(condition & (sample_properties.c.tracker == "mod"))
        )
        s3m_statement = (
            select(*_BASE_COLUMNS, s3m_sample_properties.c.filename, module.c.hash)
            .select_from(_S3M_JOIN)
            .where(condition)
        )
        xm_rows = self._connection.execute(xm_statement).fetchall()
        it_rows = self._connection.execute(it_statement).fetchall()
        mod_rows = self._connection.execute(mod_statement).fetchall()
        s3m_rows = self._connection.execute(s3m_statement).fetchall()
        properties = (
            [_row_to_xm_properties(row) for row in xm_rows]
            + [_row_to_it_properties(row) for row in it_rows]
            + [_row_to_mod_properties(row) for row in mod_rows]
            + [_row_to_s3m_properties(row) for row in s3m_rows]
        )
        return tuple(
            sorted(
                properties,
                key=lambda item: (
                    item.occurrence.module_hash,
                    item.occurrence.instrument_index,
                    item.occurrence.sample_slot,
                ),
            )
        )

    def _module_id(self, module_hash: str) -> int:
        row = self._connection.execute(select(module.c.id).where(module.c.hash == module_hash)).fetchone()
        if row is None:
            raise ValueError(f"no module ingested with hash {module_hash}")

        return int(row.id)

    def _insert_base(self, module_id: int, properties: TrackerSampleProperties) -> None:
        loop = properties.loop
        statement = insert(sample_properties).values(
            module_id=module_id,
            instrument_index=properties.occurrence.instrument_index,
            sample_slot=properties.occurrence.sample_slot,
            sample_hash=properties.sample_hash,
            tracker=properties.tracker.value,
            name=properties.name,
            rate=properties.rate,
            volume=properties.volume,
            panning=properties.panning,
            loop_begin=loop.begin if loop is not None else None,
            loop_end=loop.end if loop is not None else None,
            loop_mode=loop.mode.value if loop is not None else None,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=[
                sample_properties.c.module_id,
                sample_properties.c.instrument_index,
                sample_properties.c.sample_slot,
            ]
        )
        self._connection.execute(statement)

    def _insert_xm(self, module_id: int, properties: XMSampleProperties) -> None:
        statement = insert(xm_sample_properties).values(
            module_id=module_id,
            instrument_index=properties.occurrence.instrument_index,
            sample_slot=properties.occurrence.sample_slot,
            relative_note=properties.tuning.relative_note,
            finetune=properties.tuning.finetune,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=[
                xm_sample_properties.c.module_id,
                xm_sample_properties.c.instrument_index,
                xm_sample_properties.c.sample_slot,
            ]
        )
        self._connection.execute(statement)

    def _insert_it(self, module_id: int, properties: ITSampleProperties) -> None:
        sustain_loop = properties.sustain_loop
        vibrato = properties.vibrato
        statement = insert(it_sample_properties).values(
            module_id=module_id,
            instrument_index=properties.occurrence.instrument_index,
            sample_slot=properties.occurrence.sample_slot,
            global_volume=properties.global_volume,
            sustain_begin=sustain_loop.begin if sustain_loop is not None else None,
            sustain_end=sustain_loop.end if sustain_loop is not None else None,
            sustain_mode=sustain_loop.mode.value if sustain_loop is not None else None,
            filename=properties.filename,
            vibrato_speed=vibrato.speed if vibrato is not None else None,
            vibrato_depth=vibrato.depth if vibrato is not None else None,
            vibrato_rate=vibrato.rate if vibrato is not None else None,
            vibrato_waveform=vibrato.waveform if vibrato is not None else None,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=[
                it_sample_properties.c.module_id,
                it_sample_properties.c.instrument_index,
                it_sample_properties.c.sample_slot,
            ]
        )
        self._connection.execute(statement)

    def _insert_s3m(self, module_id: int, properties: S3MSampleProperties) -> None:
        statement = insert(s3m_sample_properties).values(
            module_id=module_id,
            instrument_index=properties.occurrence.instrument_index,
            sample_slot=properties.occurrence.sample_slot,
            filename=properties.filename,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=[
                s3m_sample_properties.c.module_id,
                s3m_sample_properties.c.instrument_index,
                s3m_sample_properties.c.sample_slot,
            ]
        )
        self._connection.execute(statement)


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


def _row_to_xm_properties(row: Row[Any]) -> XMSampleProperties:
    """Reconstruct an XMSampleProperties from a Core row, addressed by its own column names."""
    return XMSampleProperties(
        sample_hash=row.sample_hash,
        occurrence=SampleOccurrence(
            module_hash=row.hash, instrument_index=row.instrument_index, sample_slot=row.sample_slot
        ),
        name=row.name,
        rate=row.rate,
        volume=row.volume,
        panning=row.panning,
        loop=_loop_from_row(row.loop_begin, row.loop_end, row.loop_mode),
        tuning=Tuning(relative_note=row.relative_note, finetune=row.finetune),
    )


def _row_to_mod_properties(row: Row[Any]) -> MODSampleProperties:
    """Reconstruct a MODSampleProperties from a Core row, addressed by its own column names."""
    return MODSampleProperties(
        sample_hash=row.sample_hash,
        occurrence=SampleOccurrence(
            module_hash=row.hash, instrument_index=row.instrument_index, sample_slot=row.sample_slot
        ),
        name=row.name,
        rate=row.rate,
        volume=row.volume,
        panning=row.panning,
        loop=_loop_from_row(row.loop_begin, row.loop_end, row.loop_mode),
    )


def _row_to_s3m_properties(row: Row[Any]) -> S3MSampleProperties:
    """Reconstruct an S3MSampleProperties from a Core row, addressed by its own column names."""
    return S3MSampleProperties(
        sample_hash=row.sample_hash,
        occurrence=SampleOccurrence(
            module_hash=row.hash, instrument_index=row.instrument_index, sample_slot=row.sample_slot
        ),
        name=row.name,
        rate=row.rate,
        volume=row.volume,
        panning=row.panning,
        loop=_loop_from_row(row.loop_begin, row.loop_end, row.loop_mode),
        filename=row.filename,
    )


def _row_to_it_properties(row: Row[Any]) -> ITSampleProperties:
    """Reconstruct an ITSampleProperties from a Core row, addressed by its own column names."""
    return ITSampleProperties(
        sample_hash=row.sample_hash,
        occurrence=SampleOccurrence(
            module_hash=row.hash, instrument_index=row.instrument_index, sample_slot=row.sample_slot
        ),
        name=row.name,
        rate=row.rate,
        volume=row.volume,
        panning=row.panning,
        loop=_loop_from_row(row.loop_begin, row.loop_end, row.loop_mode),
        global_volume=row.global_volume,
        sustain_loop=_loop_from_row(row.sustain_begin, row.sustain_end, row.sustain_mode),
        filename=row.filename,
        vibrato=_vibrato_from_row(row.vibrato_speed, row.vibrato_depth, row.vibrato_rate, row.vibrato_waveform),
    )
