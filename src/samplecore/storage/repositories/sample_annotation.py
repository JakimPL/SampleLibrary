from __future__ import annotations

from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.models.annotation import AnnotationSource, SampleAnnotation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.curation import sample_annotation
from samplecore.storage.database import HASH_CHUNK_SIZE

# Every column but the key, read off the table itself. A write replaces a sample's whole annotation,
# so this list is that contract rather than a copy of it: a hand-kept tuple missing a column would
# quietly preserve the old value of whatever it forgot.
_REPLACED_COLUMN_NAMES: Final[tuple[str, ...]] = tuple(
    name for name in sample_annotation.c.keys() if name != "sample_hash"
)


class SampleAnnotationRepository(Protocol):
    """Persistence for what a person decides about samples by hand: a label, a rating, a favorite."""

    def get(self, sample_hash: str) -> SampleAnnotation | None: ...

    def annotations_by_hash(self, hashes: list[str]) -> dict[str, SampleAnnotation]: ...

    def list_all(self) -> tuple[SampleAnnotation, ...]: ...

    def replace_many(self, annotations: tuple[SampleAnnotation, ...]) -> None: ...

    def delete_many(self, hashes: tuple[str, ...]) -> int: ...

    def count(self) -> int: ...

    def vocabulary(self) -> tuple[str, ...]: ...


class PostgresSampleAnnotationRepository:
    """A SampleAnnotationRepository backed by the ``curation.sample_annotation`` table.

    ``replace_many`` writes a sample's annotation whole, since what a person last decided is what
    the row should say, and it is the single write path for both a lone sample and a whole group --
    a group gesture arrives here as the several rows it expands to.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, sample_hash: str) -> SampleAnnotation | None:
        statement = select(sample_annotation).where(sample_annotation.c.sample_hash == sample_hash)
        row = self._connection.execute(statement).fetchone()
        return _row_to_sample_annotation(row) if row is not None else None

    def annotations_by_hash(self, hashes: list[str]) -> dict[str, SampleAnnotation]:
        """The annotation held for each of ``hashes`` that carries one, for filling read models.

        Chunked by ``HASH_CHUNK_SIZE`` so a whole-catalog lookup stays within Postgres's own
        parameter ceiling, matching how the sample repository reads names for the same rows.
        """
        if not hashes:
            return {}

        annotations: dict[str, SampleAnnotation] = {}
        for chunk_start in range(0, len(hashes), HASH_CHUNK_SIZE):
            chunk = hashes[chunk_start : chunk_start + HASH_CHUNK_SIZE]
            statement = select(sample_annotation).where(sample_annotation.c.sample_hash.in_(chunk))
            annotations.update(
                {row.sample_hash: _row_to_sample_annotation(row) for row in self._connection.execute(statement)}
            )

        return annotations

    def list_all(self) -> tuple[SampleAnnotation, ...]:
        statement = select(sample_annotation).order_by(
            sample_annotation.c.annotated_at, sample_annotation.c.sample_hash
        )
        return tuple(_row_to_sample_annotation(row) for row in self._connection.execute(statement).fetchall())

    def replace_many(self, annotations: tuple[SampleAnnotation, ...]) -> None:
        if not annotations:
            return

        statement = insert(sample_annotation).values(
            [_sample_annotation_to_values(annotation) for annotation in annotations]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[sample_annotation.c.sample_hash],
            set_={name: statement.excluded[name] for name in _REPLACED_COLUMN_NAMES},
        )
        self._connection.execute(statement)

    def delete_many(self, hashes: tuple[str, ...]) -> int:
        """Remove the annotations held for ``hashes``, reporting how many rows actually went."""
        if not hashes:
            return 0

        result = self._connection.execute(delete(sample_annotation).where(sample_annotation.c.sample_hash.in_(hashes)))
        return result.rowcount

    def count(self) -> int:
        # pylint: disable-next=not-callable
        return self._connection.execute(select(func.count()).select_from(sample_annotation)).scalar_one()

    def vocabulary(self) -> tuple[str, ...]:
        """Every distinct label in use, most-used first, so a person is offered their own wording.

        Free text drifts, and nothing constrains what a label may say; offering back what has
        already been chosen is what keeps one vocabulary rather than several spellings of it. Rows
        that record only a rating or a favorite hold no wording, so the labels alone are gathered.
        """
        # pylint: disable-next=not-callable
        usage = func.count().label("usage")
        statement = (
            select(sample_annotation.c.label, usage)
            .where(sample_annotation.c.label.is_not(None))
            .group_by(sample_annotation.c.label)
            .order_by(usage.desc(), sample_annotation.c.label)
        )
        return tuple(row.label for row in self._connection.execute(statement).fetchall())


def _sample_annotation_to_values(annotation: SampleAnnotation) -> dict[str, Any]:
    return {
        "sample_hash": annotation.sample_hash,
        "label": annotation.label,
        "rating": annotation.rating,
        "favorite": annotation.favorite,
        "module_hash": annotation.occurrence.module_hash,
        "module_filename": annotation.module_filename,
        "instrument_index": annotation.occurrence.instrument_index,
        "sample_slot": annotation.occurrence.sample_slot,
        "sample_name": annotation.sample_name,
        "source": annotation.source.value,
        "annotated_at": annotation.annotated_at,
    }


def _row_to_sample_annotation(row: Row[Any]) -> SampleAnnotation:
    """Reconstruct a `SampleAnnotation` from a Core row, addressed by its own column names."""
    return SampleAnnotation(
        sample_hash=row.sample_hash,
        label=row.label,
        rating=row.rating,
        favorite=row.favorite,
        occurrence=SampleOccurrence(
            module_hash=row.module_hash,
            instrument_index=row.instrument_index,
            sample_slot=row.sample_slot,
        ),
        module_filename=row.module_filename,
        sample_name=row.sample_name,
        source=AnnotationSource(row.source),
        annotated_at=row.annotated_at,
    )
