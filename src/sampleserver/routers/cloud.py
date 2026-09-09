from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Connection
from trackmod.schema.scalars import Rate

from samplecore.categorization import classify_sample_category
from samplecore.models.annotation import SampleAnnotation
from samplecore.models.base import FROZEN
from samplecore.models.category import SampleCategory
from samplecore.models.cloud import ModuleCloudCoordinate
from samplecore.models.scalars import SampleHash
from samplecore.pitch import choose_playback_rate
from samplecore.storage.repositories.cloud import (
    PostgresCloudCoordinateRepository,
    PostgresModuleCloudCoordinateRepository,
)
from samplecore.storage.repositories.playback_rate import PostgresSamplePlaybackRateRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from sampleserver.dependencies import get_connection

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
