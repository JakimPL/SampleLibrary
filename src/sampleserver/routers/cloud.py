from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.categorization import classify_sample_category
from samplecore.labeling.labels import LabelPath, written_paths
from samplecore.models.annotation import SampleAnnotation
from samplecore.models.base import FROZEN
from samplecore.models.category import SampleCategory
from samplecore.models.cloud import ModuleCloudCoordinate
from samplecore.models.experiment import VOCABULARY_PARAMETER
from samplecore.models.label_suggestion import SampleLabelSuggestion
from samplecore.models.scalars import SampleHash
from samplecore.pitch import choose_playback_rate
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from samplecore.storage.repositories.playback_rate import (
    PostgresSamplePlaybackRateRepository,
)
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import (
    PostgresSampleAnnotationRepository,
)
from sampleserver.dependencies import get_connection
from sampleserver.routers.curation import TagSummary

router = APIRouter(prefix="/cloud", tags=["cloud"])


class SampleCloudPoint(BaseModel):
    """One sample's place in the embedding, with what a viewer needs to color and hear the point.

    ``category`` is computed the same way `SampleSummary.category` is -- at read time, from the
    sample's own occurrence names together with the names of the instruments reaching it -- rather
    than stored alongside the coordinate itself. ``playback_rate_hz`` travels with the point so
    clicking one plays it at the speed the library really sounds it at; it is ``None`` for a sample
    the catalog knows no rate for. ``hand_label`` carries what a person decided this sample is, for a
    viewer inspecting a point; the cloud keeps coloring by ``category``, whose fourteen roles hold a
    fixed hue each.

    This carries the coordinate's own fields rather than inheriting them, since a view of the whole
    catalog is a hundred thousand of these at once: when the run that placed them was computed says
    nothing about any one point, and a timestamp per point is several megabytes over the wire.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    x: float
    y: float
    category: SampleCategory
    hand_label: str | None
    playback_rate_hz: Rate | None


@router.get("")
def get_cloud(connection: Connection = Depends(get_connection)) -> tuple[SampleCloudPoint, ...]:
    """Every sample's position in the library's 2D embedding space, as of the latest embedding run.

    Every lookup behind a point is read whole rather than per hash: this route answers for the entire
    catalog, and asking Postgres about a hundred thousand named hashes costs it more than reading
    each table outright.
    """
    coordinates = PostgresCloudCoordinateRepository(connection).list_all()
    repository = PostgresSampleRepository(connection)
    names_by_hash, rates_by_hash = repository.names_and_rates_for_every_sample()
    instrument_names_by_hash = repository.instrument_names_for_every_sample()
    annotation_by_hash = {
        annotation.sample_hash: annotation for annotation in PostgresSampleAnnotationRepository(connection).list_all()
    }
    playback_rate_by_hash = PostgresSamplePlaybackRateRepository(connection).list_all()
    return tuple(
        SampleCloudPoint(
            sample_hash=coordinate.sample_hash,
            x=coordinate.x,
            y=coordinate.y,
            category=classify_sample_category(
                names_by_hash.get(coordinate.sample_hash, ()) + instrument_names_by_hash.get(coordinate.sample_hash, ())
            ),
            hand_label=_label_of(annotation_by_hash.get(coordinate.sample_hash)),
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
    sample the current embedding holds no point for is simply not painted.
    """
    return tuple(
        CloudLabel(sample_hash=annotation.sample_hash, paths=written_paths(annotation.label))
        for annotation in PostgresSampleAnnotationRepository(connection).list_all()
        if annotation.label is not None
    )


class CloudSuggestion(BaseModel):
    """What a listening model hears one sample as: its suggested tag paths, closest first, with their scores.

    The first path is the one a viewer paints the point with, the way the first written tag of a
    hand label is; the scores travel beside the paths so a viewer inspecting a point sees how sure
    the model was of each.
    """

    model_config = FROZEN

    sample_hash: SampleHash
    paths: tuple[tuple[str, ...], ...]
    scores: tuple[float, ...]


@router.get("/suggestions")
def get_cloud_suggestions(connection: Connection = Depends(get_connection)) -> tuple[CloudSuggestion, ...]:
    """Every sample's suggested tags from the newest scoring, for coloring the cloud by what a model hears.

    These travel apart from the points the way the hand labels do: a scoring changes only when a
    pass writes a new one, and a viewer joins them to the points by hash. An empty answer says no
    scoring has been written.
    """
    grouped: dict[str, list[SampleLabelSuggestion]] = defaultdict(list)
    for suggestion in _latest_suggestions(connection):
        grouped[suggestion.sample_hash].append(suggestion)
    return tuple(
        CloudSuggestion(
            sample_hash=sample_hash,
            paths=tuple(_path_of(suggestion) for suggestion in suggestions),
            scores=tuple(suggestion.score for suggestion in suggestions),
        )
        for sample_hash, suggestions in grouped.items()
    )


@router.get("/suggestion-tags")
def get_cloud_suggestion_tags(connection: Connection = Depends(get_connection)) -> tuple[TagSummary, ...]:
    """Every tag the newest scoring suggests first for some sample, with how many and a lasting rank.

    A specification counts toward its category the way a written label's does, so the legend can
    paint by category while the suggestions name what is under it. The rank is the tag's place in
    the vocabulary the scoring ranked, recorded with the scoring, a category taking the place of
    its first entry, so a tag keeps its color across the scorings that share a vocabulary; a tag
    the vocabulary leaves unnamed ranks after the vocabulary, by name.
    """
    repository = PostgresSampleLabelSuggestionRepository(connection)
    latest = repository.latest_experiment_id()
    if latest is None:
        return ()

    first_picks: Counter[LabelPath] = Counter()
    for label, sample_count in repository.first_pick_counts(latest).items():
        path, *_ = written_paths(label)
        for prefix in _prefixes(path):
            first_picks[prefix] += sample_count
    ranks = _vocabulary_ranks(connection, latest, first_picks)
    return tuple(
        TagSummary(path=path, sample_count=count, rank=ranks[path])
        for path, count in sorted(first_picks.items(), key=lambda item: ranks[item[0]])
    )


@router.get("/modules")
def get_module_cloud(connection: Connection = Depends(get_connection)) -> tuple[ModuleCloudCoordinate, ...]:
    """Every module's placeholder position in the library's 2D embedding space.

    Placeholder until a spectral-distance-based per-module embedding replaces it -- see
    `samplecloud.placeholder_modules`.
    """
    return PostgresModuleCloudCoordinateRepository(connection).list_all()


def _label_of(annotation: SampleAnnotation | None) -> str | None:
    """The wording a person gave this sample, where they gave one."""
    return annotation.label if annotation is not None else None


def _latest_suggestions(connection: Connection) -> tuple[SampleLabelSuggestion, ...]:
    repository = PostgresSampleLabelSuggestionRepository(connection)
    latest = repository.latest_experiment_id()
    return repository.list_for_experiment(latest) if latest is not None else ()


def _path_of(suggestion: SampleLabelSuggestion) -> LabelPath:
    """A suggestion's label as one tag path, the way a written label's first tag is read."""
    path, *_ = written_paths(suggestion.label)
    return path


def _vocabulary_ranks(connection: Connection, experiment_id: int, picked: Counter[LabelPath]) -> dict[LabelPath, int]:
    """Each picked tag's rank: its place in the scoring's vocabulary, the rest after it by name."""
    experiment = PostgresExperimentRepository(connection).get(experiment_id)
    recorded = experiment.params.get(VOCABULARY_PARAMETER, []) if experiment is not None else []
    ranks: dict[LabelPath, int] = {}
    for label in recorded if isinstance(recorded, list) else []:
        path, *_ = written_paths(str(label))
        for prefix in _prefixes(path):
            ranks.setdefault(prefix, len(ranks))
    for path in sorted(picked):
        ranks.setdefault(path, len(ranks))
    return ranks


def _prefixes(path: LabelPath) -> tuple[LabelPath, ...]:
    """A tag and every category above it, the way a written label asserts them all."""
    return tuple(path[:depth] for depth in range(1, len(path) + 1))
