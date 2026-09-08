from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.categorization import classify_sample_category
from samplecore.equivalence_classes import classes_by_member_hash, compute_equivalence_classes
from samplecore.models.base import FROZEN
from samplecore.models.category import SampleCategory
from samplecore.models.module import Module
from samplecore.models.note_event import SampleNoteUsage
from samplecore.models.relation import SampleRelation
from samplecore.models.sample import Sample, SampleSummary
from samplecore.models.sample_properties import TrackerSampleProperties
from samplecore.models.scalars import Count, ModuleHash, SampleHash
from samplecore.models.tracker import TrackerFormat
from samplecore.naming import choose_dominant_name, choose_dominant_rate
from samplecore.pitch import sounding_rate_hz
from samplecore.spectral_distance import euclidean_distance, nearest_neighbors
from samplecore.storage import audio_store
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.note_event import PostgresNoteEventRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_label import PostgresSampleLabelRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplecore.storage.repositories.spectral import PostgresSampleSpectralFeatureRepository
from samplecore.waveform import DEFAULT_WAVEFORM_BUCKET_COUNT, WaveformPeak, compute_waveform_peaks
from sampleserver.dependencies import get_connection, get_library_root
from sampleserver.equivalence import equivalence_class_members
from sampleserver.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page

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


class SampleDistance(BaseModel):
    """The spectral distance between two samples' persisted, standardized feature vectors."""

    model_config = FROZEN

    sample_hash: SampleHash
    other_hash: SampleHash
    distance: float


class SimilarSample(BaseModel):
    """One neighbor in a sample's spectral-distance nearest-neighbor listing.

    ``dominant_rate_hz`` travels with the neighbor so a listener hears it at a real tracker rate
    rather than at the stored file's own header rate; it is ``None`` for a sample with no occurrences.
    """

    model_config = FROZEN

    hash: SampleHash
    distance: float
    dominant_rate_hz: Rate | None


class SampleNotePlayed(BaseModel):
    """One note a sample is heard at, with how often the library plays it there.

    ``sounding_rate_hz`` reads the note against the sample's dominant occurrence rate, which is the
    rate a preview would otherwise play at, so a caller can sound the sample as the library really
    uses it rather than at its bare reference rate.
    """

    model_config = FROZEN

    sounded_note: int
    note_name: str
    event_count: Count
    sounding_rate_hz: float | None


class SampleDetail(Sample):
    """A sample together with every module occurrence that references it, and the notes it is played at.

    ``hand_label`` is the category a person chose for this sample, and ``category`` beside it stays
    the keyword table's guess, so a reader sees both what was decided and what was inferred.
    """

    occurrences: tuple[SampleOccurrenceDetail, ...]
    size_bytes: Count
    display_name: str
    category: SampleCategory
    hand_label: str | None
    dominant_rate_hz: Rate | None
    duration_seconds: float
    notes_played: tuple[SampleNotePlayed, ...]
    equivalence_member_count: Count


@router.get("")
def list_samples(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    group_by_equivalence: bool = False,
    connection: Connection = Depends(get_connection),
) -> Page[SampleSummary]:
    """A page of cataloged samples, ranked by how many module occurrences reference each one.

    Ranks by sample identity: one row per exact content hash. Every row still carries its
    equivalence class, when it has one; ``group_by_equivalence`` additionally collapses same-page
    rows that share a class into one representative, leaving the page's own size and offset
    meaning unchanged -- a class split across two pages collapses only on the page it appears on.
    """
    relations = PostgresSampleRelationRepository(connection).list_all()
    class_by_hash = classes_by_member_hash(compute_equivalence_classes(relations))

    repository = PostgresSampleRepository(connection)
    items = repository.list_page(limit=limit, offset=offset, class_by_hash=class_by_hash)
    total = repository.count()
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


@router.get("/{sample_hash}")
def get_sample(sample_hash: str, connection: Connection = Depends(get_connection)) -> SampleDetail:
    """One sample's own fields plus every module occurrence that references it.

    ``equivalence_member_count`` travels with the sample so a caller labeling it knows how many
    near-duplicates the same choice would reach.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")

    label = PostgresSampleLabelRepository(connection).get(sample_hash)
    properties = PostgresSamplePropertiesRepository(connection).list_for_sample(sample_hash)
    modules_by_hash = _modules_by_hash(connection, properties)
    occurrences = tuple(
        SampleOccurrenceDetail(properties=item, module=_occurrence_module(modules_by_hash[item.occurrence.module_hash]))
        for item in properties
    )
    dominant_rate_hz = choose_dominant_rate(item.rate for item in properties)
    notes_played = tuple(
        _note_played(usage, dominant_rate_hz=dominant_rate_hz)
        for usage in PostgresNoteEventRepository(connection).note_usage_for_sample(sample_hash)
    )
    return SampleDetail(
        hash=sample.hash,
        depth=sample.depth,
        channels=sample.channels,
        frames=sample.frames,
        occurrences=occurrences,
        size_bytes=sample.stored_bytes,
        display_name=choose_dominant_name(item.name for item in properties),
        category=classify_sample_category(
            tuple(item.name for item in properties)
            + PostgresSampleRepository(connection).instrument_names_by_hash([sample.hash]).get(sample.hash, ())
        ),
        hand_label=label.label if label is not None else None,
        dominant_rate_hz=dominant_rate_hz,
        duration_seconds=sample.frames / audio_store.NOMINAL_WAV_RATE,
        notes_played=notes_played,
        equivalence_member_count=len(equivalence_class_members(connection, sample_hash)),
    )


def _note_played(usage: SampleNoteUsage, *, dominant_rate_hz: Rate | None) -> SampleNotePlayed:
    """One note usage rendered for the API, sounded against the sample's dominant occurrence rate."""
    return SampleNotePlayed(
        sounded_note=usage.sounded_note.value,
        note_name=str(usage.sounded_note),
        event_count=usage.event_count,
        sounding_rate_hz=(
            None
            if dominant_rate_hz is None
            else sounding_rate_hz(reference_rate_hz=dominant_rate_hz, sounded_note=usage.sounded_note)
        ),
    )


@router.get("/{sample_hash}/audio")
def get_sample_audio(
    sample_hash: str,
    connection: Connection = Depends(get_connection),
    library_root: Path = Depends(get_library_root),
) -> FileResponse:
    """The sample's own canonical audio, as stored in the content-addressable store.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    if PostgresSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")

    return FileResponse(audio_store.object_path(library_root, sample_hash), media_type="audio/wav")


@router.get("/{sample_hash}/waveform")
def get_sample_waveform(
    sample_hash: str,
    connection: Connection = Depends(get_connection),
    library_root: Path = Depends(get_library_root),
) -> tuple[WaveformPeak, ...]:
    """A compact amplitude-envelope preview of the sample's own waveform.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    sample = PostgresSampleRepository(connection).get(sample_hash)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")

    pcm = audio_store.read(library_root, sample).pcm
    return compute_waveform_peaks(pcm, bucket_count=DEFAULT_WAVEFORM_BUCKET_COUNT)


@router.get("/{sample_hash}/relations")
def get_sample_relations(
    sample_hash: str, connection: Connection = Depends(get_connection)
) -> tuple[SampleRelation, ...]:
    """Every equivalence-class link this sample participates in, on either side of the pair.

    Raises:
        HTTPException: 404 when no sample is cataloged under this hash.
    """
    if PostgresSampleRepository(connection).get(sample_hash) is None:
        raise HTTPException(status_code=404, detail=f"no sample cataloged with hash {sample_hash!r}")

    return PostgresSampleRelationRepository(connection).list_for_sample(sample_hash)


@router.get("/{sample_hash}/distance/{other_hash}")
def get_sample_distance(
    sample_hash: str, other_hash: str, connection: Connection = Depends(get_connection)
) -> SampleDistance:
    """The Euclidean distance between two samples' persisted, standardized spectral feature vectors.

    Raises:
        HTTPException: 404 when either sample has no persisted spectral feature vector yet -- not
            yet embedded, or embedded before this metric existed.
    """
    repository = PostgresSampleSpectralFeatureRepository(connection)
    subject = repository.get(sample_hash)
    reference = repository.get(other_hash)
    if subject is None or reference is None:
        raise HTTPException(status_code=404, detail="one or both samples have no spectral feature vector yet")

    return SampleDistance(
        sample_hash=sample_hash, other_hash=other_hash, distance=euclidean_distance(subject.vector, reference.vector)
    )


@router.get("/{sample_hash}/similar")
def get_similar_samples(
    sample_hash: str,
    limit: Annotated[int, Query(ge=1, le=MAX_SIMILAR_SAMPLES_LIMIT)] = DEFAULT_SIMILAR_SAMPLES_LIMIT,
    connection: Connection = Depends(get_connection),
) -> tuple[SimilarSample, ...]:
    """The catalog's samples whose spectral feature vector sits closest to this one's, nearest first.

    Raises:
        HTTPException: 404 when this sample has no persisted spectral feature vector yet.
    """
    features = PostgresSampleSpectralFeatureRepository(connection).list_all()
    vectors_by_hash = {feature.sample_hash: feature.vector for feature in features}
    if sample_hash not in vectors_by_hash:
        raise HTTPException(status_code=404, detail=f"sample {sample_hash!r} has no spectral feature vector yet")

    neighbors = nearest_neighbors(sample_hash, vectors_by_hash, limit=limit)
    _, rates_by_hash = PostgresSampleRepository(connection).names_and_rates_by_hash(
        [neighbor_hash for neighbor_hash, _ in neighbors]
    )
    return tuple(
        SimilarSample(
            hash=neighbor_hash,
            distance=distance,
            dominant_rate_hz=choose_dominant_rate(rates_by_hash.get(neighbor_hash, ())),
        )
        for neighbor_hash, distance in neighbors
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
