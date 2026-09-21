from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, func, select
from sqlalchemy.dialects.postgresql import insert as upsert

from samplecore.models.sample_category import CategoryPromotion, SampleCategory, SampleTopCategory
from samplecore.storage.database import (
    HASH_CHUNK_SIZE,
    PROMOTION_SLOT,
    bulk_insert,
    category_promotion,
    chunks,
    sample_category,
)

_COLUMN_NAMES: Final[tuple[str, ...]] = ("experiment_id", "sample_hash", "rank", "label", "score", "computed_at")


class SampleCategoryRepository(Protocol):
    """Persistence for the categories a listening model assigns per sample, scoped to one experiment."""

    def insert_many(self, categories: Sequence[SampleCategory]) -> None: ...

    def list_for_experiment(self, experiment_id: int) -> tuple[SampleCategory, ...]: ...

    def get_many(self, experiment_id: int, sample_hashes: list[str]) -> dict[str, tuple[SampleCategory, ...]]: ...

    def top_category_labels(self, experiment_id: int, sample_hashes: list[str]) -> dict[str, str]: ...

    def top_categories(self, experiment_id: int) -> tuple[SampleTopCategory, ...]: ...

    def top_category_counts(self, experiment_id: int) -> dict[str, int]: ...

    def shown_experiment_id(self) -> int | None: ...


class PostgresSampleCategoryRepository:
    """A SampleCategoryRepository backed by the catalog's ``sample_category`` table.

    A scoring writes every sample's categories once under its own experiment, so ``insert_many``
    needs no conflict resolution.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert_many(self, categories: Sequence[SampleCategory]) -> None:
        if not categories:
            return

        bulk_insert(
            self._connection,
            sample_category,
            _COLUMN_NAMES,
            (
                (
                    category.experiment_id,
                    category.sample_hash,
                    category.rank,
                    category.label,
                    category.score,
                    category.computed_at,
                )
                for category in categories
            ),
        )

    def list_for_experiment(self, experiment_id: int) -> tuple[SampleCategory, ...]:
        """Every category of one scoring, each sample's in rank order."""
        statement = (
            select(sample_category)
            .where(sample_category.c.experiment_id == experiment_id)
            .order_by(sample_category.c.sample_hash, sample_category.c.rank)
        )
        return tuple(_row_to_category(row) for row in self._connection.execute(statement))

    def get_many(self, experiment_id: int, sample_hashes: list[str]) -> dict[str, tuple[SampleCategory, ...]]:
        """One scoring's categories for the given samples, in rank order, leaving out samples it holds none for.

        Chunked by ``HASH_CHUNK_SIZE`` so a whole-catalog lookup stays within Postgres's own
        parameter ceiling, the same way every other by-hash lookup does.
        """
        by_hash: dict[str, list[SampleCategory]] = defaultdict(list)
        for chunk in chunks(sample_hashes, HASH_CHUNK_SIZE):
            statement = (
                select(sample_category)
                .where(sample_category.c.experiment_id == experiment_id)
                .where(sample_category.c.sample_hash.in_(chunk))
                .order_by(sample_category.c.rank)
            )
            for row in self._connection.execute(statement):
                by_hash[row.sample_hash].append(_row_to_category(row))

        return {sample_hash: tuple(categories) for sample_hash, categories in by_hash.items()}

    def top_category_labels(self, experiment_id: int, sample_hashes: list[str]) -> dict[str, str]:
        """One scoring's top category for the given samples, leaving out those it reached none of.

        The label alone, which is what names a sample wherever it is listed; a reader wanting the
        score behind it asks for the sample's whole ranking. Chunked by ``HASH_CHUNK_SIZE`` like
        every other by-hash lookup, so a whole page of hashes stays within Postgres's parameter
        ceiling.
        """
        labels: dict[str, str] = {}
        for chunk in chunks(sample_hashes, HASH_CHUNK_SIZE):
            statement = (
                select(sample_category.c.sample_hash, sample_category.c.label)
                .where(sample_category.c.experiment_id == experiment_id)
                .where(sample_category.c.rank == 0)
                .where(sample_category.c.sample_hash.in_(chunk))
            )
            for row in self._connection.execute(statement):
                labels[row.sample_hash] = str(row.label)

        return labels

    def top_categories(self, experiment_id: int) -> tuple[SampleTopCategory, ...]:
        """One scoring's top category per sample: the three columns a whole-catalog view paints by."""
        statement = (
            select(sample_category.c.sample_hash, sample_category.c.label, sample_category.c.score)
            .where(sample_category.c.experiment_id == experiment_id)
            .where(sample_category.c.rank == 0)
            .order_by(sample_category.c.sample_hash)
        )
        return tuple(
            SampleTopCategory(sample_hash=row.sample_hash, label=row.label, score=row.score)
            for row in self._connection.execute(statement)
        )

    def top_category_counts(self, experiment_id: int) -> dict[str, int]:
        """How many samples one scoring gives each label as its top category, counted where the rows are."""
        # pylint: disable-next=not-callable
        counted = func.count().label("sample_count")
        statement = (
            select(sample_category.c.label, counted)
            .where(sample_category.c.experiment_id == experiment_id)
            .where(sample_category.c.rank == 0)
            .group_by(sample_category.c.label)
        )
        return {str(row.label): int(row.sample_count) for row in self._connection.execute(statement)}

    def shown_experiment_id(self) -> int | None:
        """The scoring the application shows, or nothing when no scoring has been shown."""
        promotion = PostgresCategoryPromotionRepository(self._connection).current()
        return promotion.experiment_id if promotion is not None else None


class PostgresCategoryPromotionRepository:
    """The one-row record of which scoring the application shows."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def record(self, promotion: CategoryPromotion) -> None:
        """Make ``promotion`` the scoring on show, replacing whichever one was."""
        statement = upsert(category_promotion).values(
            slot=PROMOTION_SLOT, experiment_id=promotion.experiment_id, promoted_at=promotion.promoted_at
        )
        statement = statement.on_conflict_do_update(
            index_elements=[category_promotion.c.slot],
            set_={"experiment_id": statement.excluded.experiment_id, "promoted_at": statement.excluded.promoted_at},
        )
        self._connection.execute(statement)

    def current(self) -> CategoryPromotion | None:
        """The scoring on show, or nothing when no scoring has been shown."""
        row = self._connection.execute(select(category_promotion)).fetchone()
        if row is None:
            return None
        return CategoryPromotion(experiment_id=row.experiment_id, promoted_at=row.promoted_at)


def _row_to_category(row: Row[Any]) -> SampleCategory:
    return SampleCategory(
        experiment_id=row.experiment_id,
        sample_hash=row.sample_hash,
        rank=row.rank,
        label=row.label,
        score=row.score,
        computed_at=row.computed_at,
    )
