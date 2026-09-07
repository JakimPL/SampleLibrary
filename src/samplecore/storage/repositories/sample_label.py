from __future__ import annotations

from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.label import LabelSource, SampleLabel
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.curation import sample_label
from samplecore.storage.database import HASH_CHUNK_SIZE

_UPDATABLE_COLUMN_NAMES: Final[tuple[str, ...]] = (
    "label",
    "module_hash",
    "module_filename",
    "instrument_index",
    "sample_slot",
    "sample_name",
    "source",
    "labeled_at",
)


class SampleLabelRepository(Protocol):
    """Persistence for the categories a person assigns to samples by hand."""

    def get(self, sample_hash: str) -> SampleLabel | None: ...

    def labels_by_hash(self, hashes: list[str]) -> dict[str, str]: ...

    def list_all(self) -> tuple[SampleLabel, ...]: ...

    def upsert_many(self, labels: tuple[SampleLabel, ...]) -> None: ...

    def delete_many(self, hashes: tuple[str, ...]) -> int: ...

    def count(self) -> int: ...

    def vocabulary(self) -> tuple[str, ...]: ...


class PostgresSampleLabelRepository:
    """A SampleLabelRepository backed by the ``curation.sample_label`` table.

    ``upsert_many`` replaces a sample's label outright, since a person relabelling a sample means
    the new choice, and it is the single write path for both a lone sample and a whole group -- a
    group gesture arrives here as the several rows it expands to.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, sample_hash: str) -> SampleLabel | None:
        statement = select(sample_label).where(sample_label.c.sample_hash == sample_hash)
        row = self._connection.execute(statement).fetchone()
        return _row_to_sample_label(row) if row is not None else None

    def labels_by_hash(self, hashes: list[str]) -> dict[str, str]:
        """The label text held for each of ``hashes`` that carries one, for filling read models.

        Chunked by ``HASH_CHUNK_SIZE`` so a whole-catalog lookup stays within Postgres's own
        parameter ceiling, matching how the sample repository reads names for the same rows.
        """
        if not hashes:
            return {}

        labels: dict[str, str] = {}
        for chunk_start in range(0, len(hashes), HASH_CHUNK_SIZE):
            chunk = hashes[chunk_start : chunk_start + HASH_CHUNK_SIZE]
            statement = select(sample_label.c.sample_hash, sample_label.c.label).where(
                sample_label.c.sample_hash.in_(chunk)
            )
            labels.update({row.sample_hash: row.label for row in self._connection.execute(statement).fetchall()})

        return labels

    def list_all(self) -> tuple[SampleLabel, ...]:
        statement = select(sample_label).order_by(sample_label.c.labeled_at, sample_label.c.sample_hash)
        return tuple(_row_to_sample_label(row) for row in self._connection.execute(statement).fetchall())

    def upsert_many(self, labels: tuple[SampleLabel, ...]) -> None:
        if not labels:
            return

        statement = insert(sample_label).values([_sample_label_to_values(label) for label in labels])
        statement = statement.on_conflict_do_update(
            index_elements=[sample_label.c.sample_hash],
            set_={name: statement.excluded[name] for name in _UPDATABLE_COLUMN_NAMES},
        )
        self._connection.execute(statement)

    def delete_many(self, hashes: tuple[str, ...]) -> int:
        """Remove the labels held for ``hashes``, reporting how many rows actually went."""
        if not hashes:
            return 0

        result = self._connection.execute(delete(sample_label).where(sample_label.c.sample_hash.in_(hashes)))
        return result.rowcount

    def count(self) -> int:
        # pylint: disable-next=not-callable
        return self._connection.execute(select(func.count()).select_from(sample_label)).scalar_one()

    def vocabulary(self) -> tuple[str, ...]:
        """Every distinct label in use, most-used first, so a person is offered their own wording.

        Free text drifts, and nothing constrains what a label may say; offering back what has
        already been chosen is what keeps one vocabulary rather than several spellings of it.
        """
        # pylint: disable-next=not-callable
        usage = func.count().label("usage")
        statement = (
            select(sample_label.c.label, usage)
            .group_by(sample_label.c.label)
            .order_by(usage.desc(), sample_label.c.label)
        )
        return tuple(row.label for row in self._connection.execute(statement).fetchall())


def _sample_label_to_values(label: SampleLabel) -> dict[str, Any]:
    return {
        "sample_hash": label.sample_hash,
        "label": label.label,
        "module_hash": label.occurrence.module_hash,
        "module_filename": label.module_filename,
        "instrument_index": label.occurrence.instrument_index,
        "sample_slot": label.occurrence.sample_slot,
        "sample_name": label.sample_name,
        "source": label.source.value,
        "labeled_at": label.labeled_at,
    }


def _row_to_sample_label(row: Row[Any]) -> SampleLabel:
    """Reconstruct a `SampleLabel` from a Core row, addressed by its own column names."""
    return SampleLabel(
        sample_hash=row.sample_hash,
        label=row.label,
        occurrence=SampleOccurrence(
            module_hash=row.module_hash,
            instrument_index=row.instrument_index,
            sample_slot=row.sample_slot,
        ),
        module_filename=row.module_filename,
        sample_name=row.sample_name,
        source=LabelSource(row.source),
        labeled_at=row.labeled_at,
    )
