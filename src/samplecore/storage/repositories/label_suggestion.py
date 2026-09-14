from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Final, Protocol

from sqlalchemy import Connection, Row, func, select
from sqlalchemy.dialects.postgresql import insert as upsert

from samplecore.models.label_suggestion import SampleFirstPick, SampleLabelSuggestion, SuggestionPromotion
from samplecore.storage.database import (
    HASH_CHUNK_SIZE,
    PROMOTION_SLOT,
    bulk_insert,
    chunks,
    sample_label_suggestion,
    suggestion_promotion,
)

_COLUMN_NAMES: Final[tuple[str, ...]] = ("experiment_id", "sample_hash", "rank", "label", "score", "computed_at")


class SampleLabelSuggestionRepository(Protocol):
    """Persistence for the labels a listening model suggests per sample, scoped to one experiment."""

    def insert_many(self, suggestions: Sequence[SampleLabelSuggestion]) -> None: ...

    def list_for_experiment(self, experiment_id: int) -> tuple[SampleLabelSuggestion, ...]: ...

    def get_many(
        self, experiment_id: int, sample_hashes: list[str]
    ) -> dict[str, tuple[SampleLabelSuggestion, ...]]: ...

    def first_picks_for_experiment(self, experiment_id: int) -> tuple[SampleFirstPick, ...]: ...

    def first_pick_counts(self, experiment_id: int) -> dict[str, int]: ...

    def shown_experiment_id(self) -> int | None: ...


class PostgresSampleLabelSuggestionRepository:
    """A SampleLabelSuggestionRepository backed by the catalog's ``sample_label_suggestion`` table.

    A scoring writes every sample's suggestions once under its own experiment, so ``insert_many``
    needs no conflict resolution.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert_many(self, suggestions: Sequence[SampleLabelSuggestion]) -> None:
        if not suggestions:
            return

        bulk_insert(
            self._connection,
            sample_label_suggestion,
            _COLUMN_NAMES,
            (
                (
                    suggestion.experiment_id,
                    suggestion.sample_hash,
                    suggestion.rank,
                    suggestion.label,
                    suggestion.score,
                    suggestion.computed_at,
                )
                for suggestion in suggestions
            ),
        )

    def list_for_experiment(self, experiment_id: int) -> tuple[SampleLabelSuggestion, ...]:
        """Every suggestion of one scoring, each sample's in rank order."""
        statement = (
            select(sample_label_suggestion)
            .where(sample_label_suggestion.c.experiment_id == experiment_id)
            .order_by(sample_label_suggestion.c.sample_hash, sample_label_suggestion.c.rank)
        )
        return tuple(_row_to_suggestion(row) for row in self._connection.execute(statement))

    def get_many(self, experiment_id: int, sample_hashes: list[str]) -> dict[str, tuple[SampleLabelSuggestion, ...]]:
        """One scoring's suggestions for the given samples, in rank order, leaving out samples it holds none for.

        Chunked by ``HASH_CHUNK_SIZE`` so a whole-catalog lookup stays within Postgres's own
        parameter ceiling, the same way every other by-hash lookup does.
        """
        by_hash: dict[str, list[SampleLabelSuggestion]] = defaultdict(list)
        for chunk in chunks(sample_hashes, HASH_CHUNK_SIZE):
            statement = (
                select(sample_label_suggestion)
                .where(sample_label_suggestion.c.experiment_id == experiment_id)
                .where(sample_label_suggestion.c.sample_hash.in_(chunk))
                .order_by(sample_label_suggestion.c.rank)
            )
            for row in self._connection.execute(statement):
                by_hash[row.sample_hash].append(_row_to_suggestion(row))

        return {sample_hash: tuple(suggestions) for sample_hash, suggestions in by_hash.items()}

    def first_picks_for_experiment(self, experiment_id: int) -> tuple[SampleFirstPick, ...]:
        """One scoring's closest suggestion per sample: the three columns a whole-catalog view paints by."""
        statement = (
            select(
                sample_label_suggestion.c.sample_hash, sample_label_suggestion.c.label, sample_label_suggestion.c.score
            )
            .where(sample_label_suggestion.c.experiment_id == experiment_id)
            .where(sample_label_suggestion.c.rank == 0)
            .order_by(sample_label_suggestion.c.sample_hash)
        )
        return tuple(
            SampleFirstPick(sample_hash=row.sample_hash, label=row.label, score=row.score)
            for row in self._connection.execute(statement)
        )

    def first_pick_counts(self, experiment_id: int) -> dict[str, int]:
        """How many samples one scoring suggests each label for first, counted where the rows are."""
        # pylint: disable-next=not-callable
        counted = func.count().label("sample_count")
        statement = (
            select(sample_label_suggestion.c.label, counted)
            .where(sample_label_suggestion.c.experiment_id == experiment_id)
            .where(sample_label_suggestion.c.rank == 0)
            .group_by(sample_label_suggestion.c.label)
        )
        return {str(row.label): int(row.sample_count) for row in self._connection.execute(statement)}

    def shown_experiment_id(self) -> int | None:
        """The scoring the application shows, or nothing when no scoring has been shown."""
        promotion = PostgresSuggestionPromotionRepository(self._connection).current()
        return promotion.experiment_id if promotion is not None else None


class PostgresSuggestionPromotionRepository:
    """The one-row record of which scoring the application shows."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def record(self, promotion: SuggestionPromotion) -> None:
        """Make ``promotion`` the scoring on show, replacing whichever one was."""
        statement = upsert(suggestion_promotion).values(
            slot=PROMOTION_SLOT, experiment_id=promotion.experiment_id, promoted_at=promotion.promoted_at
        )
        statement = statement.on_conflict_do_update(
            index_elements=[suggestion_promotion.c.slot],
            set_={"experiment_id": statement.excluded.experiment_id, "promoted_at": statement.excluded.promoted_at},
        )
        self._connection.execute(statement)

    def current(self) -> SuggestionPromotion | None:
        """The scoring on show, or nothing when no scoring has been shown."""
        row = self._connection.execute(select(suggestion_promotion)).fetchone()
        if row is None:
            return None
        return SuggestionPromotion(experiment_id=row.experiment_id, promoted_at=row.promoted_at)


def _row_to_suggestion(row: Row[Any]) -> SampleLabelSuggestion:
    return SampleLabelSuggestion(
        experiment_id=row.experiment_id,
        sample_hash=row.sample_hash,
        rank=row.rank,
        label=row.label,
        score=row.score,
        computed_at=row.computed_at,
    )
