from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from samplecore.digests import digest_of_rows
from samplecore.models.annotation import (
    AnnotationAnchor,
    AnnotationSource,
    ModuleSlotAnchor,
    SampleAnnotation,
    SampleFileAnchor,
)
from samplecore.models.sample_file import SampleFileLocation
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.curation import sample_annotation
from samplecore.storage.database import HASH_CHUNK_SIZE, POSTGRES_PARAMETER_LIMIT, chunks, sample

# Every column but the key, read off the table itself. A write replaces a sample's whole annotation,
# so this list is that contract rather than a copy of it: a hand-kept tuple missing a column would
# quietly preserve the old value of whatever it forgot.
_REPLACED_COLUMN_NAMES: Final[tuple[str, ...]] = tuple(
    name for name in sample_annotation.c.keys() if name != "sample_hash"
)
ANNOTATION_ROWS_PER_STATEMENT: Final[int] = POSTGRES_PARAMETER_LIMIT // len(sample_annotation.c)


class SampleAnnotationRepository(Protocol):
    """Persistence for what a person decides about samples by hand: a label, a rating, a favorite."""

    def get(self, sample_hash: str) -> SampleAnnotation | None: ...

    def annotations_by_hash(self, hashes: list[str]) -> dict[str, SampleAnnotation]: ...

    def list_all(self) -> tuple[SampleAnnotation, ...]: ...

    def upsert_many(self, annotations: tuple[SampleAnnotation, ...]) -> None: ...

    def delete_many(self, hashes: tuple[str, ...]) -> int: ...

    def cataloged_labels(self) -> dict[str, str]: ...

    def count(self) -> int: ...

    def vocabulary(self) -> tuple[str, ...]: ...


class PostgresSampleAnnotationRepository:
    """A SampleAnnotationRepository backed by the ``curation.sample_annotation`` table.

    ``upsert_many`` writes each sample's annotation whole, as the caller merged it, and it is the
    single write path for a lone sample, a whole group and an imported file alike -- a group gesture
    arrives here as the several rows it expands to.
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
        for chunk in chunks(hashes, HASH_CHUNK_SIZE):
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

    def upsert_many(self, annotations: tuple[SampleAnnotation, ...]) -> None:
        """Write each annotation whole over whatever its sample held, in statements Postgres binds.

        Raises:
            ValueError: two annotations name one sample, which leaves no one thing for its row to say.
        """
        repeated = sorted(
            sample_hash
            for sample_hash, occurrences in Counter(annotation.sample_hash for annotation in annotations).items()
            if occurrences > 1
        )
        if repeated:
            raise ValueError(f"one write names these samples more than once: {', '.join(repeated)}")

        for batch in chunks(annotations, ANNOTATION_ROWS_PER_STATEMENT):
            statement = insert(sample_annotation).values([_sample_annotation_to_values(item) for item in batch])
            statement = statement.on_conflict_do_update(
                index_elements=[sample_annotation.c.sample_hash],
                set_={name: statement.excluded[name] for name in _REPLACED_COLUMN_NAMES},
            )
            self._connection.execute(statement)

    def delete_many(self, hashes: tuple[str, ...]) -> int:
        """Remove the annotations held for ``hashes``, reporting how many rows actually went."""
        removed = 0
        for chunk in chunks(hashes, HASH_CHUNK_SIZE):
            result = self._connection.execute(
                delete(sample_annotation).where(sample_annotation.c.sample_hash.in_(chunk))
            )
            removed += result.rowcount
        return removed

    def cataloged_labels(self) -> dict[str, str]:
        """Each cataloged sample's hand label, for a viewer drawing the catalog's samples alone."""
        statement = (
            select(sample_annotation.c.sample_hash, sample_annotation.c.label)
            .join(sample, sample.c.hash == sample_annotation.c.sample_hash)
            .where(sample_annotation.c.label.is_not(None))
        )
        return {row.sample_hash: row.label for row in self._connection.execute(statement)}

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

    def label_digest(self) -> str:
        """One digest over every hand label by sample, so a pass taught by the labels can tell whether one changed.

        Ratings and favorites stay out of it, since nothing trained on the labels reads them.
        """
        statement = (
            select(sample_annotation.c.sample_hash, sample_annotation.c.label)
            .where(sample_annotation.c.label.is_not(None))
            .order_by(sample_annotation.c.sample_hash)
        )
        return digest_of_rows((str(row.sample_hash), str(row.label)) for row in self._connection.execute(statement))


def _sample_annotation_to_values(annotation: SampleAnnotation) -> dict[str, Any]:
    return {
        "sample_hash": annotation.sample_hash,
        "label": annotation.label,
        "rating": annotation.rating,
        "favorite": annotation.favorite,
        **_anchor_values(annotation.anchor),
        "source": annotation.source.value,
        "annotated_at": annotation.annotated_at,
    }


def _anchor_values(anchor: AnnotationAnchor) -> dict[str, str | int | None]:
    """The anchor columns of a row, those of the anchor's own kind filled and the others left empty."""
    match anchor:
        case ModuleSlotAnchor():
            return {
                "module_hash": anchor.occurrence.module_hash,
                "module_filename": anchor.module_filename,
                "instrument_index": anchor.occurrence.instrument_index,
                "sample_slot": anchor.occurrence.sample_slot,
                "sample_name": anchor.sample_name,
                "file_directory": None,
                "file_relative_path": None,
            }
        case SampleFileAnchor():
            return {
                "module_hash": None,
                "module_filename": None,
                "instrument_index": None,
                "sample_slot": None,
                "sample_name": None,
                "file_directory": anchor.location.directory.as_posix(),
                "file_relative_path": anchor.location.relative_path,
            }


def _row_to_sample_annotation(row: Row[Any]) -> SampleAnnotation:
    """Reconstruct a `SampleAnnotation` from a Core row, addressed by its own column names."""
    return SampleAnnotation(
        sample_hash=row.sample_hash,
        label=row.label,
        rating=row.rating,
        favorite=row.favorite,
        anchor=_row_to_anchor(row),
        source=AnnotationSource(row.source),
        annotated_at=row.annotated_at,
    )


def _row_to_anchor(row: Row[Any]) -> AnnotationAnchor:
    """The anchor a row holds, told apart by which anchor's columns are filled, as the table's CHECK keeps them."""
    if row.module_hash is None:
        return SampleFileAnchor(
            location=SampleFileLocation(directory=Path(row.file_directory), relative_path=row.file_relative_path)
        )
    return ModuleSlotAnchor(
        occurrence=SampleOccurrence(
            module_hash=row.module_hash, instrument_index=row.instrument_index, sample_slot=row.sample_slot
        ),
        module_filename=row.module_filename,
        sample_name=row.sample_name,
    )
