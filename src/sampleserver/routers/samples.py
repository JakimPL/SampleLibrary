from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.categorization import classify_sample_names
from samplecore.equivalence_classes import classes_by_member_hash, compute_equivalence_classes
from samplecore.models.base import FROZEN
from samplecore.models.category import SampleCategory
from samplecore.models.module import Module
from samplecore.models.note_event import SamplePlaybackRate
from samplecore.models.relation import SampleRelation
from samplecore.models.sample import DescribedSample, SampleSelection, SampleSort, SampleSummary
from samplecore.models.sample_file import SampleFileLocation
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.models.scalars import (
    MAXIMUM_RATING,
    MINIMUM_RATING,
    Count,
    ModuleHash,
    SampleHash,
)
from samplecore.models.tracker import TrackerFormat
from samplecore.naming import NO_SAMPLE_NAMES
from samplecore.pitch import (
    playback_rates_of,
    tally_playback_rates,
)
from samplecore.spectral_distance import SpectralVectors, euclidean_distance, nearest_neighbors
from samplecore.storage import audio_store
from samplecore.storage.playback_rates import resolved_playback_rates
from samplecore.storage.repositories.label_suggestion import PostgresSampleLabelSuggestionRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository, peaks_from_thumbnail
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError, is_unchanged
from samplecore.waveform import WaveformPeak
from sampleserver.caching import IMMUTABLE_CACHE_CONTROL
from sampleserver.dependencies import (
    ConnectionOpener,
    get_connection,
    get_connection_opener,
    get_library_root,
    get_spectral_vectors,
)
from sampleserver.equivalence import equivalence_class_members
from sampleserver.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from sampleserver.parameters import MAX_PAGE_OFFSET, NOT_FOUND_RESPONSE, WAV_CONTENT, WAV_MEDIA_TYPE, SampleHashPath

router = APIRouter(prefix="/samples", tags=["samples"])

DEFAULT_SIMILAR_SAMPLES_LIMIT: Final[int] = 10
MAX_SIMILAR_SAMPLES_LIMIT: Final[int] = 50


class SampleOccurrenceModule(BaseModel):
    """The module context a sample occurrence belongs to, resolved for display alongside it."""

    model_config = FROZEN

    hash: ModuleHash
    filename: str
    title: str
    tracker: TrackerFormat


class SampleOccurrenceDetail(BaseModel):
    """One module occurrence of a sample, together with the module it belongs to."""

    model_config = FROZEN

    properties: TrackerSampleProperties
    module: SampleOccurrenceModule


class SampleFileDetail(BaseModel):
    """One file a sample was found in, read in place from a sample directory.

    ``available`` says whether the file is there now with the size and write time it was scanned
    at, which is what playing the sample from it needs.
    """

    model_config = FROZEN

    location: SampleFileLocation
    rate: Rate
    available: bool


class SampleDistance(BaseModel):
    """The spectral distance between two samples' persisted, standardized feature vectors."""

    model_config = FROZEN

    sample_hash: SampleHash
    other_hash: SampleHash
    distance: float


class SamplePreview(BaseModel):
    """What a glance at a sample shows: its name, category and hand label, and the stored thumbnail of its waveform.

    ``thumbnail`` is ``None`` for a sample the thumbnail pass has not reached, since a preview
    with nothing to draw is still a preview with a name.
    """

    model_config = FROZEN

    display_name: str
    category: SampleCategory
    hand_label: str | None
    thumbnail: tuple[WaveformPeak, ...] | None


class SimilarSample(SamplePreview):
    """One neighbor in a sample's spectral-distance nearest-neighbor listing: a glance at it, how far it sits, and the rate to hear it at.

    ``playback_rate_hz`` travels with the neighbor so a listener hears it at the speed the library
    really plays it; it is ``None`` for a sample the catalog knows no rate for.
    """

    hash: SampleHash
    distance: float
    playback_rate_hz: Rate | None


class SuggestedLabel(BaseModel):
    """One tag a listening model suggests for a sample, in the hand-label grammar, and how sure it was."""

    model_config = FROZEN

    label: str
    score: float


class SampleDetail(DescribedSample):
    """A sample together with every module occurrence and sample file holding it, and the rates it is heard at.

    ``playback_rates`` holds every effective rate the library sounds this sample at, the most played
    first, so a listener can hear each of them; ``playback_rate_hz`` is the first of them.
    ``suggested_labels`` are what the scoring on show of the listening model hears the sample as,
    closest first, for a person to accept into the hand label or pass over.
    """

    occurrences: tuple[SampleOccurrenceDetail, ...]
    files: tuple[SampleFileDetail, ...]
    duration_seconds: float
    playback_rates: tuple[SamplePlaybackRate, ...]
    equivalence_member_count: Count
    suggested_labels: tuple[SuggestedLabel, ...]


def get_selection(
    favorites_only: bool = False,
    minimum_rating: Annotated[int | None, Query(ge=MINIMUM_RATING, le=MAXIMUM_RATING)] = None,
    sort: SampleSort = SampleSort.OCCURRENCES,
) -> SampleSelection:
    """Read a listing's narrowing and ordering off the query string.

    Gathered as a dependency so the three arrive as one value: a query-parameter model expands only
    where it is the sole ``Query`` on a route, and this listing pages with ``limit`` and ``offset``
    beside it.
    """
    return SampleSelection(favorites_only=favorites_only, minimum_rating=minimum_rating, sort=sort)


@router.get("")
def list_samples(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_PAGE_OFFSET)] = 0,
    group_by_equivalence: bool = False,
    selection: SampleSelection = Depends(get_selection),
    connection: Connection = Depends(get_connection),
) -> Page[SampleSummary]:
    """A page of the catalog's samples, narrowed and ordered by what a person has decided.

    ``favorites_only`` and ``minimum_rating`` reach the whole catalog rather than one page, so a
    collection scattered across a hundred thousand samples still browses as a collection.
    ``group_by_equivalence`` collapses same-page rows sharing an equivalence class afterwards, which
    is why the total counts rows rather than groups.
    """
    relations = PostgresSampleRelationRepository(connection).list_all()
    class_by_hash = classes_by_member_hash(compute_equivalence_classes(relations))

    repository = PostgresSampleRepository(connection)
    items = repository.list_page(limit=limit, offset=offset, class_by_hash=class_by_hash, selection=selection)
    total = repository.count(selection=selection)
    if group_by_equivalence:
        items = _collapse_by_equivalence(items)

    return Page(items=items, total=total, limit=limit, offset=offset)


def _collapse_by_equivalence(items: tuple[SampleSummary, ...]) -> tuple[SampleSummary, ...]:
    """Collapse same-page rows sharing an equivalence class into one representative each.

    The representative is the member with the highest occurrence count, ties broken by ascending
    hash; every other member of that class on this page is dropped from the result. A row with no
    class passes through unchanged. Each representative keeps its own ``equivalence_member_count``,
    which already reflects the class's whole-catalog size, not merely how many members are visible
    on this page.
    """
    representative_index_by_class: dict[str, int] = {}
    collapsed: list[SampleSummary] = []
    for item in items:
        if item.equivalence_class_hash is None:
            collapsed.append(item)
            continue

        index = representative_index_by_class.get(item.equivalence_class_hash)
        if index is None:
            representative_index_by_class[item.equivalence_class_hash] = len(collapsed)
            collapsed.append(item)
            continue

        current = collapsed[index]
        is_better = item.occurrence_count > current.occurrence_count or (
            item.occurrence_count == current.occurrence_count and item.hash < current.hash
        )
        if is_better:
            collapsed[index] = item

    return tuple(collapsed)


@router.get("/{sample_hash}", responses=NOT_FOUND_RESPONSE)
def get_sample(sample_hash: SampleHashPath, connection: Connection = Depends(get_connection)) -> SampleDetail:
    """One sample's own fields plus every module occurrence and sample file holding it.

    ``equivalence_member_count`` travels with the sample so a caller labeling it knows how many
    near-duplicates the same choice would reach. ``playback_rate_hz`` is the rate every reader
    of the catalog plays the sample at, and ``playback_rates`` lists every rate its note events
    strike it at, as they stand in the catalog.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")

    annotation = PostgresSampleAnnotationRepository(connection).get(sample_hash)
    properties = PostgresSamplePropertiesRepository(connection).list_for_sample(sample_hash)
    modules_by_hash = _modules_by_hash(connection, properties)
    occurrences = tuple(
        SampleOccurrenceDetail(properties=item, module=_occurrence_module(modules_by_hash[item.occurrence.module_hash]))
        for item in properties
    )
    tally = tally_playback_rates(PostgresNoteEventRepository(connection).note_usage_for_sample(sample_hash))
    names_by_hash, _ = PostgresSampleRepository(connection).names_and_rates_by_hash([sample_hash])
    names = names_by_hash.get(sample_hash, NO_SAMPLE_NAMES)
    return SampleDetail(
        hash=sample.hash,
        depth=sample.depth,
        channels=sample.channels,
        frames=sample.frames,
        occurrences=occurrences,
        files=tuple(
            SampleFileDetail(location=found.location, rate=found.rate, available=is_unchanged(found))
            for found in PostgresSampleFileRepository(connection).list_for_samples([sample_hash])
        ),
        size_bytes=sample.stored_bytes,
        display_name=names.display_name,
        category=classify_sample_names(names),
        hand_label=annotation.label if annotation is not None else None,
        rating=annotation.rating if annotation is not None else None,
        favorite=annotation.favorite if annotation is not None else False,
        playback_rate_hz=resolved_playback_rates(connection, [sample_hash])[sample_hash],
        duration_seconds=sample.frames / audio_store.NOMINAL_WAV_RATE,
        playback_rates=playback_rates_of(tally),
        equivalence_member_count=len(equivalence_class_members(connection, sample_hash)),
        suggested_labels=_suggested_labels(connection, sample_hash),
    )


def _suggested_labels(connection: Connection, sample_hash: str) -> tuple[SuggestedLabel, ...]:
    """The shown scoring's suggestions for one sample, closest first; none for a sample it did not reach."""
    repository = PostgresSampleLabelSuggestionRepository(connection)
    shown = repository.shown_experiment_id()
    if shown is None:
        return ()
    return tuple(
        SuggestedLabel(label=suggestion.label, score=suggestion.score)
        for suggestion in repository.get_many(shown, [sample_hash]).get(sample_hash, ())
    )


@router.get(
    "/{sample_hash}/audio",
    response_class=FileResponse,
    responses={200: {"content": WAV_CONTENT}, **NOT_FOUND_RESPONSE},
)
def get_sample_audio(
    sample_hash: SampleHashPath,
    library_root: Path = Depends(get_library_root),
    open_connection: ConnectionOpener = Depends(get_connection_opener),
) -> Response:
    """The sample's own canonical audio: its stored object, or the WAV the store would hold for it.

    A stored object is read straight off the store by its hash, with no catalog round trip on the
    way to a sound: the hash's own shape is checked on the path, which is what keeps a request inside
    the store. A sample found in a sample file is read from the file the catalog names and encoded
    the way the store encodes an object, so both kinds play at the same nominal header rate. Either
    way the bytes are those of the hash, so they are served with a cache lifetime of a year.

    Raises:
        HTTPException: 404 when the store holds no object under this hash and no cataloged file
            holds the sample now.
    """
    path = audio_store.object_path(library_root, sample_hash)
    if path.is_file():
        return FileResponse(path, media_type=WAV_MEDIA_TYPE, headers={"Cache-Control": IMMUTABLE_CACHE_CONTROL})

    with open_connection() as connection:
        sample_files = PostgresSampleFileRepository(connection).list_for_samples([sample_hash])
    try:
        sample_pcm = SampleAudio.of_files(library_root, sample_files).read_by_hash(sample_hash)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"no sample stored with hash {sample_hash!r}") from error
    except SampleUnavailableError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return Response(
        audio_store.encode_wav(sample_pcm),
        media_type=WAV_MEDIA_TYPE,
        headers={"Cache-Control": IMMUTABLE_CACHE_CONTROL},
    )


@router.get("/{sample_hash}/preview", responses=NOT_FOUND_RESPONSE)
def get_sample_preview(sample_hash: SampleHashPath, connection: Connection = Depends(get_connection)) -> SamplePreview:
    """A sample as a hover shows it, read from what the catalog already holds and nothing decoded.

    Four narrow lookups answer this, against the eight a detail makes: a tooltip appears on every
    point a cursor crosses, so it costs what a glance is worth.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    if PostgresSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")

    return _previews_by_hash(connection, [sample_hash])[sample_hash]


def _previews_by_hash(connection: Connection, sample_hashes: list[str]) -> dict[str, SamplePreview]:
    """A glance at each given sample, from four lookups over the whole list at once."""
    names_by_hash, _ = PostgresSampleRepository(connection).names_and_rates_by_hash(sample_hashes)
    annotations_by_hash = PostgresSampleAnnotationRepository(connection).annotations_by_hash(sample_hashes)
    thumbnails_by_hash = PostgresSampleThumbnailRepository(connection).get_many(sample_hashes)
    previews: dict[str, SamplePreview] = {}
    for sample_hash in sample_hashes:
        names = names_by_hash.get(sample_hash, NO_SAMPLE_NAMES)
        annotation = annotations_by_hash.get(sample_hash)
        previews[sample_hash] = SamplePreview(
            display_name=names.display_name,
            category=classify_sample_names(names),
            hand_label=annotation.label if annotation is not None else None,
            thumbnail=peaks_from_thumbnail(thumbnails_by_hash.get(sample_hash)),
        )
    return previews


@router.get("/{sample_hash}/relations", responses=NOT_FOUND_RESPONSE)
def get_sample_relations(
    sample_hash: SampleHashPath, connection: Connection = Depends(get_connection)
) -> tuple[SampleRelation, ...]:
    """Every equivalence-class link this sample participates in, on either side of the pair.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    if PostgresSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")

    return PostgresSampleRelationRepository(connection).list_for_sample(sample_hash)


@router.get("/{sample_hash}/distance/{other_hash}", responses=NOT_FOUND_RESPONSE)
def get_sample_distance(
    sample_hash: SampleHashPath, other_hash: SampleHashPath, connection: Connection = Depends(get_connection)
) -> SampleDistance:
    """The Euclidean distance between two samples' persisted, standardized spectral feature vectors.

    Raises:
        HTTPException: 404 when either sample is not cataloged, or has no persisted spectral feature
            vector yet -- not yet embedded, or embedded before this metric existed.
    """
    for named_hash in (sample_hash, other_hash):
        _require_cataloged(connection, named_hash)
    repository = PostgresSampleSpectralFeatureRepository(connection)
    subject = repository.get(sample_hash)
    reference = repository.get(other_hash)
    if subject is None or reference is None:
        raise HTTPException(status_code=404, detail="one or both samples have no spectral feature vector yet")

    return SampleDistance(
        sample_hash=sample_hash, other_hash=other_hash, distance=euclidean_distance(subject.vector, reference.vector)
    )


@router.get("/{sample_hash}/similar", responses=NOT_FOUND_RESPONSE)
def get_similar_samples(
    sample_hash: SampleHashPath,
    limit: Annotated[int, Query(ge=1, le=MAX_SIMILAR_SAMPLES_LIMIT)] = DEFAULT_SIMILAR_SAMPLES_LIMIT,
    connection: Connection = Depends(get_connection),
    vectors: SpectralVectors = Depends(get_spectral_vectors),
) -> tuple[SimilarSample, ...]:
    """The catalog's samples whose spectral feature vector sits closest to this one's, nearest first.

    Every neighbor is found by measuring this sample against the whole catalog at once, over the
    vectors held parsed for as long as the embedding behind them stands. Each arrives with what a
    glance shows, so a listing reads and plays without opening any of them.

    Raises:
        HTTPException: 404 when this sample is not cataloged, or has no persisted spectral feature vector yet.
    """
    _require_cataloged(connection, sample_hash)
    if sample_hash not in vectors.row_by_hash:
        raise HTTPException(status_code=404, detail=f"sample {sample_hash!r} has no spectral feature vector yet")

    neighbors = nearest_neighbors(sample_hash, vectors, limit=limit)
    neighbor_hashes = [neighbor_hash for neighbor_hash, _ in neighbors]
    previews_by_hash = _previews_by_hash(connection, neighbor_hashes)
    playback_rate_by_hash = resolved_playback_rates(connection, neighbor_hashes)
    return tuple(
        _similar_sample(
            previews_by_hash[neighbor_hash],
            sample_hash=neighbor_hash,
            distance=distance,
            playback_rate_hz=playback_rate_by_hash[neighbor_hash],
        )
        for neighbor_hash, distance in neighbors
    )


def _require_cataloged(connection: Connection, sample_hash: str) -> None:
    """Refuse a hash the catalog holds no sample under, before asking after anything computed from one.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    if PostgresSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")


def _similar_sample(
    preview: SamplePreview, *, sample_hash: str, distance: float, playback_rate_hz: Rate | None
) -> SimilarSample:
    return SimilarSample(
        display_name=preview.display_name,
        category=preview.category,
        hand_label=preview.hand_label,
        thumbnail=preview.thumbnail,
        hash=sample_hash,
        distance=distance,
        playback_rate_hz=playback_rate_hz,
    )


def _modules_by_hash(connection: Connection, properties: tuple[TrackerSampleProperties, ...]) -> dict[str, Module]:
    hashes = sorted({item.occurrence.module_hash for item in properties})
    modules_by_hash = PostgresModuleRepository(connection).get_many(hashes)
    for module_hash in hashes:
        if module_hash not in modules_by_hash:
            raise ValueError(f"sample occurrence references module {module_hash!r}, which is not cataloged")

    return modules_by_hash


def _occurrence_module(module: Module) -> SampleOccurrenceModule:
    return SampleOccurrenceModule(
        hash=module.hash, filename=module.filename, title=module.title, tracker=module.tracker
    )
