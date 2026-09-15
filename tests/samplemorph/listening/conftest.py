from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
from sqlalchemy import Connection
from trackmod.core.samples.depth import BitDepth
from trackmod.trackers.xm.tuning import Tuning

from samplecore.models.annotation import AnnotationSource, ModuleSlotAnchor, SampleAnnotation
from samplecore.models.channels import ChannelLayout
from samplecore.models.experiment import Experiment
from samplecore.models.label_suggestion import SampleLabelSuggestion, SuggestionPromotion
from samplecore.models.module import Module
from samplecore.models.sample import Sample
from samplecore.models.sample_pcm import SamplePCM
from samplecore.models.sample_properties import SampleOccurrence, XMSampleProperties
from samplecore.models.tracker import TrackerFormat
from samplecore.storage import audio_store
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.label_suggestion import (
    PostgresSampleLabelSuggestionRepository,
    PostgresSuggestionPromotionRepository,
)
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from tests.samplemorph.conftest import harmonic_tone

CATALOG_RATE_HZ: Final[int] = 22050
TONE_FRAME_COUNT: Final[int] = 8192
LOWEST_TONE_HZ: Final[float] = 110.0
TONE_STEP_SEMITONES: Final[float] = 3.0


@dataclass(frozen=True)
class CatalogedTone:
    """One tone a test catalog holds: the label the scoring on show suggests first at its score, and the module holding it.

    `hand_label` is what a person wrote the tone is, where they wrote anything, and an inaudible
    tone is stored as frames of zeros, the way a module keeps an empty slot.
    """

    suggested_label: str
    score: float
    module_index: int
    hand_label: str | None
    audible: bool


def seed_labeled_tones(connection: Connection, library_root: Path, tones: tuple[CatalogedTone, ...]) -> tuple[str, ...]:
    """Catalog one harmonic tone per entry, each a few semitones above the last, under a scoring on show.

    A hash repeats one byte, so every tone's hash differs from every other's; the tones sharing a
    module index share one module.
    """
    now = datetime.now(UTC)
    modules: dict[int, Module] = {}
    hashes = []
    experiment_id = _shown_scoring(connection, now=now)
    for index, tone in enumerate(tones):
        sample = Sample(
            hash=f"{index + 1:02x}" * 32, depth=BitDepth.SIXTEEN, channels=ChannelLayout.MONO, frames=TONE_FRAME_COUNT
        )
        PostgresSampleRepository(connection).upsert(sample)
        frequency = LOWEST_TONE_HZ * 2.0 ** (index * TONE_STEP_SEMITONES / 12.0)
        pcm = harmonic_tone(TONE_FRAME_COUNT, frequency=frequency) if tone.audible else np.zeros((TONE_FRAME_COUNT, 1))
        audio_store.write(library_root, SamplePCM(sample=sample, pcm=pcm))
        module = modules.get(tone.module_index) or _module(connection, index=tone.module_index, now=now)
        modules[tone.module_index] = module
        occurrence = SampleOccurrence(module_hash=module.hash, instrument_index=index, sample_slot=0)
        PostgresSamplePropertiesRepository(connection).upsert(
            XMSampleProperties(
                sample_hash=sample.hash,
                occurrence=occurrence,
                name=f"tone{index}",
                rate=CATALOG_RATE_HZ,
                volume=64,
                tuning=Tuning(relative_note=0, finetune=0),
            )
        )
        PostgresSampleLabelSuggestionRepository(connection).insert_many(
            [
                SampleLabelSuggestion(
                    experiment_id=experiment_id,
                    sample_hash=sample.hash,
                    rank=0,
                    label=tone.suggested_label,
                    score=tone.score,
                    computed_at=now,
                )
            ]
        )
        if tone.hand_label is not None:
            PostgresSampleAnnotationRepository(connection).upsert_many(
                (
                    SampleAnnotation(
                        sample_hash=sample.hash,
                        label=tone.hand_label,
                        rating=None,
                        favorite=False,
                        anchor=ModuleSlotAnchor(
                            occurrence=occurrence, module_filename=module.filename, sample_name=f"tone{index}"
                        ),
                        source=AnnotationSource.SAMPLE,
                        annotated_at=now,
                    ),
                )
            )
        hashes.append(sample.hash)
    connection.commit()
    return tuple(hashes)


def _shown_scoring(connection: Connection, *, now: datetime) -> int:
    experiments = PostgresExperimentRepository(connection)
    experiment_id = experiments.next_id()
    experiments.insert(Experiment(id=experiment_id, backend_name="clap", params={}, created_at=now, label=None))
    PostgresSuggestionPromotionRepository(connection).record(
        SuggestionPromotion(experiment_id=experiment_id, promoted_at=now)
    )
    return experiment_id


def _module(connection: Connection, *, index: int, now: datetime) -> Module:
    repository = PostgresModuleRepository(connection)
    module = Module(
        id=repository.next_id(),
        hash=format(index + 900, "064x"),
        filename=f"song{index}.xm",
        tracker=TrackerFormat.XM,
        title="untitled",
        channel_count=4,
        pattern_count=1,
        instrument_count=1,
        sample_count=1,
        file_size=1024,
        ingested_at=now,
    )
    repository.insert(module)
    return module
