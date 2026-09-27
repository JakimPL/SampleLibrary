from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum, unique
from typing import Final

from psycopg import sql
from sqlalchemy import Table

from samplecore.models.experiment import VOCABULARY_PARAMETER
from samplecore.storage.curation import curation_metadata
from samplecore.storage.database import metadata

PUBLIC_SCHEMA: Final[str] = "public"


@unique
class Rule(StrEnum):
    """Which rows of one table a publication carries."""

    WHOLE = "whole"
    PUBLISHED_SAMPLES = "the published samples' rows"
    FILES_IN_PUBLISHED_DIRECTORIES = "the files of the published directories, each named by its folder"
    RELATIONS_BETWEEN_PUBLISHED = "the relations joining two published samples, with no review"
    CATEGORIES_ON_SHOW = "the published samples' categories in the scoring on show"
    SCORING_ON_SHOW = "the scoring on show, with its vocabulary alone"
    EMPTY = "none"


# Every table a catalog holds, and which of its rows a site receives. The module collection travels
# whole: every sample a module holds is published. What serves no page, and every decision a person
# made, stays home.
RULES: Final[dict[str, Rule]] = {
    "experiment": Rule.SCORING_ON_SHOW,
    "module": Rule.WHOLE,
    "pass_completion": Rule.EMPTY,
    "sample": Rule.PUBLISHED_SAMPLES,
    "category_promotion": Rule.WHOLE,
    "cloud_promotion": Rule.EMPTY,
    "module_cloud_coordinates": Rule.WHOLE,
    "module_instrument": Rule.EMPTY,
    "module_note_extraction": Rule.EMPTY,
    "sample_category": Rule.CATEGORIES_ON_SHOW,
    "sample_cloud_coordinates": Rule.PUBLISHED_SAMPLES,
    "sample_feature_vector": Rule.EMPTY,
    "sample_file": Rule.FILES_IN_PUBLISHED_DIRECTORIES,
    "sample_fingerprint": Rule.EMPTY,
    "sample_playback_rate": Rule.PUBLISHED_SAMPLES,
    "sample_properties": Rule.WHOLE,
    "sample_relation": Rule.RELATIONS_BETWEEN_PUBLISHED,
    "sample_spectral_feature": Rule.PUBLISHED_SAMPLES,
    "sample_thumbnail": Rule.PUBLISHED_SAMPLES,
    "it_sample_properties": Rule.WHOLE,
    "note_event": Rule.WHOLE,
    "s3m_sample_properties": Rule.WHOLE,
    "xm_sample_properties": Rule.WHOLE,
    "curation.annotation_history": Rule.EMPTY,
    "curation.annotation_history_start": Rule.EMPTY,
    "curation.annotation_import": Rule.EMPTY,
    "curation.sample_annotation": Rule.EMPTY,
    "curation.tag_rank": Rule.EMPTY,
}

# The samples a publication carries: every one a module holds, and every one found in a published
# directory, less any such file-only sample whose file could not be read.
PUBLISHED_SAMPLES: Final[sql.SQL] = sql.SQL(
    "WITH published AS (SELECT sample.hash FROM public.sample AS sample "
    "WHERE (EXISTS (SELECT 1 FROM public.sample_properties AS occurrence WHERE occurrence.sample_hash = sample.hash) "
    "OR EXISTS (SELECT 1 FROM public.sample_file AS found "
    "WHERE found.sample_hash = sample.hash AND found.directory = ANY(%(directories)s::text[]))) "
    "AND NOT sample.hash = ANY(%(unreadable)s::text[])) "
)
SHOWN_SCORING: Final[sql.SQL] = sql.SQL("(SELECT experiment_id FROM public.category_promotion)")


def catalog_tables() -> tuple[Table, ...]:
    """Every table a catalog holds, parents before the tables naming them, the curation tables last."""
    return (*metadata.sorted_tables, *curation_metadata.sorted_tables)


def rule_of(table: Table) -> Rule:
    """Which rows of ``table`` a publication carries.

    Raises:
        KeyError: the table has no rule, which a table added to the catalog needs before it is published.
    """
    return RULES[table.fullname]


def qualified(table: Table) -> sql.Composed:
    """The table's name qualified by its schema, as a statement on either end of a publication names it."""
    return sql.SQL(".").join((sql.Identifier(table.schema or PUBLIC_SCHEMA), sql.Identifier(table.name)))


def source_query(table: Table) -> sql.Composed | None:
    """The query reading the rows of ``table`` a publication carries, in its columns' order; ``None`` for one carrying none.

    The query takes three parameters: ``directories``, the published sample directories as the
    catalog names them; ``names``, the folder name each is published under, in the same order; and
    ``unreadable``, the file-only samples whose files could not be read.
    """
    rule = rule_of(table)
    return None if rule is Rule.EMPTY else _QUERIES[rule](table)


def _whole(table: Table) -> sql.Composed:
    return sql.SQL("SELECT {columns} FROM {table}").format(columns=_columns(table), table=qualified(table))


def _published_samples(table: Table) -> sql.Composed:
    key = sql.Identifier("hash" if table.name == "sample" else "sample_hash")
    return PUBLISHED_SAMPLES + sql.SQL(
        "SELECT {columns} FROM {table} WHERE {key} IN (SELECT hash FROM published)"
    ).format(columns=_columns(table), table=qualified(table), key=key)


def _files_in_published_directories(table: Table) -> sql.Composed:
    renamed = sql.SQL(", ").join(
        (
            sql.SQL("('/' || (%(names)s::text[])[array_position(%(directories)s::text[], directory)])")
            if column.name == "directory"
            else sql.Identifier(column.name)
        )
        for column in table.columns
    )
    return PUBLISHED_SAMPLES + sql.SQL(
        "SELECT {columns} FROM {table} WHERE directory = ANY(%(directories)s::text[]) "
        "AND sample_hash IN (SELECT hash FROM published)"
    ).format(columns=renamed, table=qualified(table))


def _relations_between_published(table: Table) -> sql.Composed:
    reviewless = sql.SQL(", ").join(
        sql.SQL("NULL") if column.name.startswith("reviewed_") else sql.Identifier(column.name)
        for column in table.columns
    )
    return PUBLISHED_SAMPLES + sql.SQL(
        "SELECT {columns} FROM {table} WHERE subject_hash IN (SELECT hash FROM published) "
        "AND reference_hash IN (SELECT hash FROM published)"
    ).format(columns=reviewless, table=qualified(table))


def _categories_on_show(table: Table) -> sql.Composed:
    return PUBLISHED_SAMPLES + sql.SQL(
        "SELECT {columns} FROM {table} WHERE experiment_id = {shown} AND sample_hash IN (SELECT hash FROM published)"
    ).format(columns=_columns(table), table=qualified(table), shown=SHOWN_SCORING)


def _scoring_on_show(table: Table) -> sql.Composed:
    trimmed = sql.SQL(", ").join(_scoring_column(column.name) for column in table.columns)
    return sql.SQL("SELECT {columns} FROM {table} WHERE id = {shown}").format(
        columns=trimmed, table=qualified(table), shown=SHOWN_SCORING
    )


def _columns(table: Table) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(column.name) for column in table.columns)


_QUERIES: Final[dict[Rule, Callable[[Table], sql.Composed]]] = {
    Rule.WHOLE: _whole,
    Rule.PUBLISHED_SAMPLES: _published_samples,
    Rule.FILES_IN_PUBLISHED_DIRECTORIES: _files_in_published_directories,
    Rule.RELATIONS_BETWEEN_PUBLISHED: _relations_between_published,
    Rule.CATEGORIES_ON_SHOW: _categories_on_show,
    Rule.SCORING_ON_SHOW: _scoring_on_show,
}


def _scoring_column(name: str) -> sql.Composable:
    """A column of the scoring on show as published: its parameters cut to its vocabulary, and no label or key."""
    match name:
        case "params":
            return sql.SQL("json_build_object({vocabulary}, params::json -> {vocabulary})::text").format(
                vocabulary=sql.Literal(VOCABULARY_PARAMETER)
            )
        case "label" | "key":
            return sql.SQL("NULL")
        case _:
            return sql.Identifier(name)
