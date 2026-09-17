from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Hashable
from datetime import datetime
from typing import Final

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.labeling.labels import LabelPath, written_paths
from samplecore.models.base import FROZEN
from samplecore.models.experiment import VOCABULARY_PARAMETER
from samplecore.models.scalars import ModuleHash, SampleHash
from samplecore.pitch import choose_playback_rate
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.playback_rate import (
    PostgresSamplePlaybackRateRepository,
)
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import (
    PostgresSampleAnnotationRepository,
)
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from sampleserver.dependencies import (
    get_cloud_cache,
    get_connection,
    get_shown_experiment_id,
    get_suggestion_tags_cache,
    get_suggestions_cache,
)
from sampleserver.response_cache import RevisionedJsonCache
from sampleserver.routers.curation import TagSummary

router = APIRouter(prefix="/cloud", tags=["cloud"])

# The viewer rescales every coordinate onto its own unit square, so four decimals place a point
# far finer than any pixel at any zoom while a full-precision float would cost twice the digits.
COORDINATE_DECIMALS: Final[int] = 4
JSON_MEDIA_TYPE: Final[str] = "application/json"
GZIP_ENCODING: Final[str] = "gzip"

CloudRevision = tuple[tuple[int, datetime | None], tuple[int, int], int, tuple[int, int]]


class SampleCloudPoint(BaseModel):
    """One sample's place in the embedding, with the rate a viewer hears the point at.

    ``playback_rate_hz`` travels with the point so clicking one plays it at the speed the library
    really sounds it at; it is ``None`` for a sample the catalog knows no rate for.

    This carries the coordinate's own fields rather than inheriting them, since a view of the whole
    catalog is a hundred thousand of these at once: when the run that placed them was computed says
    nothing about any one point, and a timestamp per point is several megabytes over the wire. What
    colors a point travels apart for the same reason: the hand labels through `/cloud/labels`, and
    what the listening model heard through `/cloud/suggestions`.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    x: float
    y: float
    playback_rate_hz: Rate | None


class ModuleCloudPoint(BaseModel):
    """One module's place in the embedding: the coordinate alone, for the same reason a sample's point is."""

    model_config = FROZEN

    module_hash: ModuleHash
    x: float
    y: float


CLOUD_POINTS: Final = TypeAdapter(tuple[SampleCloudPoint, ...])


@router.get("", response_model=tuple[SampleCloudPoint, ...])
def get_cloud(
    request: Request,
    connection: Connection = Depends(get_connection),
    cache: RevisionedJsonCache = Depends(get_cloud_cache),
) -> Response:
    """Every sample's position in the library's 2D embedding space, as of the latest embedding run.

    The answer is built once per revision of what it reads and served from memory after that: the
    coordinates' count and last write, the playback rates on file, the modules cataloged and the
    sample files scanned are what a pipeline moves, and four scalar queries say whether any has. A caller that accepts
    gzip receives the body compressed once at the best level rather than per request. The scoring on
    show belongs to the revision of `/cloud/suggestions` alone, since the points carry none of it.
    """
    revision: CloudRevision = (
        PostgresCloudCoordinateRepository(connection).revision(),
        PostgresSamplePlaybackRateRepository(connection).revision(),
        PostgresModuleRepository(connection).count(),
        PostgresSampleFileRepository(connection).revision(),
    )
    return _cached_json(request, cache, revision, lambda: CLOUD_POINTS.dump_json(_cloud_points(connection)))


def _cloud_points(connection: Connection) -> tuple[SampleCloudPoint, ...]:
    """Every lookup behind a point is read whole rather than per hash: asking Postgres about a hundred thousand named hashes costs it more than reading each table outright."""
    coordinates = PostgresCloudCoordinateRepository(connection).list_all()
    rates_by_hash = PostgresSampleRepository(connection).rates_for_every_sample()
    playback_rate_by_hash = PostgresSamplePlaybackRateRepository(connection).list_all()
    return tuple(
        SampleCloudPoint(
            sample_hash=coordinate.sample_hash,
            x=round(coordinate.x, COORDINATE_DECIMALS),
            y=round(coordinate.y, COORDINATE_DECIMALS),
            playback_rate_hz=choose_playback_rate(
                note_event_rate=playback_rate_by_hash.get(coordinate.sample_hash),
                occurrence_rates=rates_by_hash.get(coordinate.sample_hash, ()),
            ),
        )
        for coordinate in coordinates
    )


class CloudLabel(BaseModel):
    """What a person decided one sample is, as the tag paths they wrote, in the order they wrote them.

    The order is kept because a point can show one color: the tag a person wrote first is the one
    they thought of first, so it is the one a viewer paints the point with.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    paths: tuple[tuple[str, ...], ...]


@router.get("/labels")
def get_cloud_labels(connection: Connection = Depends(get_connection)) -> tuple[CloudLabel, ...]:
    """Every labeled sample's tags, for coloring the cloud by what a person decided.

    These travel apart from the points on purpose: the labels are a few hundred rows against a
    hundred thousand points, and they change with every label a person writes while the points
    change only when the embedding is recomputed. A viewer joins the two by hash, so a labeled
    sample the current embedding holds no point for is simply not painted. Labels whose sample has
    left the catalog wait for relinking and stay off the cloud.
    """
    return tuple(
        CloudLabel(sample_hash=sample_hash, paths=written_paths(label))
        for sample_hash, label in sorted(PostgresSampleAnnotationRepository(connection).cataloged_labels().items())
    )


class CloudSuggestion(BaseModel):
    """What a listening model hears one sample as first: its closest suggested tag path, and how sure it was.

    The first pick is the one a viewer paints the point with, the way the first written tag of a
    hand label is, and the one the legend counts; a sample's detail lists the picks behind it.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    path: tuple[str, ...]
    score: float


CLOUD_SUGGESTIONS: Final = TypeAdapter(tuple[CloudSuggestion, ...])
CLOUD_SUGGESTION_TAGS: Final = TypeAdapter(tuple[TagSummary, ...])


@router.get("/suggestions", response_model=tuple[CloudSuggestion, ...])
def get_cloud_suggestions(
    request: Request,
    connection: Connection = Depends(get_connection),
    cache: RevisionedJsonCache = Depends(get_suggestions_cache),
) -> Response:
    """Every sample's first suggested tag from the scoring on show, for coloring the cloud by what a model hears.

    These travel apart from the points the way the hand labels do: a scoring's suggestions never
    change once written, so the id of the scoring on show is the whole revision, and a viewer joins
    them to the points by hash. An empty answer says no scoring is shown.
    """
    repository = PostgresSampleLabelSuggestionRepository(connection)
    shown = repository.shown_experiment_id()
    return _cached_json(request, cache, shown, lambda: CLOUD_SUGGESTIONS.dump_json(_first_picks(repository, shown)))


def _first_picks(
    repository: PostgresSampleLabelSuggestionRepository, experiment_id: int | None
) -> tuple[CloudSuggestion, ...]:
    if experiment_id is None:
        return ()

    return tuple(
        CloudSuggestion(sample_hash=pick.sample_hash, path=_path_of(pick.label), score=pick.score)
        for pick in repository.first_picks_for_experiment(experiment_id)
    )


def _cached_json(
    request: Request, cache: RevisionedJsonCache, revision: Hashable, build: Callable[[], bytes]
) -> Response:
    """The cached answer in the encoding the caller takes, marked so the middleware and the caches downstream read it right."""
    accepts_gzip = GZIP_ENCODING in request.headers.get("accept-encoding", "")
    body = cache.body(revision, build, gzipped=accepts_gzip)
    headers = {"Vary": "Accept-Encoding"}
    if accepts_gzip:
        headers["Content-Encoding"] = GZIP_ENCODING
    return Response(content=body, media_type=JSON_MEDIA_TYPE, headers=headers)


@router.get("/suggestion-tags", response_model=tuple[TagSummary, ...])
def get_cloud_suggestion_tags(
    request: Request,
    connection: Connection = Depends(get_connection),
    cache: RevisionedJsonCache = Depends(get_suggestion_tags_cache),
    shown_experiment_id: int | None = Depends(get_shown_experiment_id),
) -> Response:
    """Every tag the scoring on show suggests first for some sample, with how many and a lasting rank.

    A specification counts toward its top level the way a written label's does, so the legend can
    paint by top level while the suggestions name what is under it. The rank is the tag's place in
    the vocabulary the scoring ranked, recorded with the scoring, a top level taking the place of
    its first entry, so a tag keeps its color across the scorings that share a vocabulary; a tag
    the vocabulary leaves unnamed ranks after the vocabulary, by name.

    The counts come from a group-by over every first pick in the catalog, and every badge naming a
    sample reads these ranks, so the answer is held like the suggestions beside it: a scoring's
    picks never change once written, which makes the id of the scoring on show the whole revision.
    """
    return _cached_json(
        request,
        cache,
        shown_experiment_id,
        lambda: CLOUD_SUGGESTION_TAGS.dump_json(_tags(connection, shown_experiment_id)),
    )


def _tags(connection: Connection, experiment_id: int | None) -> tuple[TagSummary, ...]:
    """The tags one scoring suggests first, each counting toward its top level, in vocabulary order."""
    if experiment_id is None:
        return ()

    repository = PostgresSampleLabelSuggestionRepository(connection)
    first_picks: Counter[LabelPath] = Counter()
    for label, sample_count in repository.first_pick_counts(experiment_id).items():
        for prefix in _prefixes(_path_of(label)):
            first_picks[prefix] += sample_count
    ranks = _vocabulary_ranks(connection, experiment_id, first_picks)
    return tuple(
        TagSummary(path=path, sample_count=count, rank=ranks[path])
        for path, count in sorted(first_picks.items(), key=lambda item: ranks[item[0]])
    )


@router.get("/modules")
def get_module_cloud(connection: Connection = Depends(get_connection)) -> tuple[ModuleCloudPoint, ...]:
    """Every module's placeholder position in the library's 2D embedding space.

    Placeholder until a spectral-distance-based per-module embedding replaces it -- see
    `samplecloud.placeholder_modules`.
    """
    return tuple(
        ModuleCloudPoint(
            module_hash=coordinate.module_hash,
            x=round(coordinate.x, COORDINATE_DECIMALS),
            y=round(coordinate.y, COORDINATE_DECIMALS),
        )
        for coordinate in PostgresModuleCloudCoordinateRepository(connection).list_all()
    )


def _path_of(label: str) -> LabelPath:
    """A suggested label as one tag path, the way a written label's first tag is read."""
    path, *_ = written_paths(label)
    return path


def _vocabulary_ranks(connection: Connection, experiment_id: int, picked: Counter[LabelPath]) -> dict[LabelPath, int]:
    """Each picked tag's rank: its place in the scoring's vocabulary, the rest after it by name."""
    experiment = PostgresExperimentRepository(connection).get(experiment_id)
    recorded = experiment.params.get(VOCABULARY_PARAMETER, []) if experiment is not None else []
    ranks: dict[LabelPath, int] = {}
    for label in recorded if isinstance(recorded, list) else []:
        for prefix in _prefixes(_path_of(str(label))):
            ranks.setdefault(prefix, len(ranks))
    for path in sorted(picked):
        ranks.setdefault(path, len(ranks))
    return ranks


def _prefixes(path: LabelPath) -> tuple[LabelPath, ...]:
    """A tag and every tag above it, the way a written label asserts them all."""
    return tuple(path[:depth] for depth in range(1, len(path) + 1))
