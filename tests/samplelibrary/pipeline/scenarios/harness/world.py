from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import soundfile
from sqlalchemy import Column, Connection, select, text

from samplecore.config import load_config
from samplecore.digests import digest_of_rows
from samplecore.models.annotation import AnnotationSource, ModuleSlotAnchor, SampleAnnotation
from samplecore.models.pass_completion import PassKind
from samplecore.models.sample_properties import SampleOccurrence
from samplecore.storage.database import (
    category_promotion,
    claim_named_lock,
    cloud_promotion,
    connect,
    experiment,
    named_lock_key,
)
from samplecore.storage.repositories.cloud import PostgresCloudCoordinateRepository
from samplecore.storage.repositories.experiment import PostgresExperimentRepository
from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
from samplecore.storage.repositories.module import PostgresModuleRepository
from samplecore.storage.repositories.pass_completion import PostgresPassCompletionRepository
from samplecore.storage.repositories.relation import PostgresSampleRelationRepository
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.repositories.sample_properties import PostgresSamplePropertiesRepository
from samplelibrary.pipeline.artifacts import SIDECAR_SUFFIX, ArtifactSidecar, read_step_record
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.layout import PipelineLayout
from samplelibrary.pipeline.locks import pipeline_lock_name, step_is_running
from samplelibrary.pipeline.scratch import RESET_STEP
from samplelibrary.pipeline.settings import PipelineSettings, read_pipeline_settings
from samplelibrary.pipeline.steps.library import library_graph
from samplelibrary.sandbox.modules import sandbox_modules
from samplelibrary.sandbox.sample_pack import sample_pack
from samplelibrary.sandbox.waveforms import SAMPLE_RATE, decaying, tonal_waveform
from samplemorph.published import read_published

# The first six of the sandbox's modules are four unrelated songs and one deliberate pair, so a
# world of this size carries an equivalence relation for the detection pass to find.
MODULE_COUNT: Final[int] = 6
PACK_FILE_COUNT: Final[int] = 2
ADDED_PACK_FRAMES: Final[int] = SAMPLE_RATE // 4
DEFAULT_PIPELINE_TABLE: Final[str] = 'memory_cap = "none"\nworkers = 1\n'
CATALOG_PARTS: Final[tuple[str, ...]] = ("modules", "samples", "relations", "files", "passes")
PARTS: Final[tuple[str, ...]] = (
    "modules",
    "samples",
    "relations",
    "files",
    "labels",
    "passes",
    "experiments",
    "categories",
    "cloud",
    "artifacts",
)


@dataclass(frozen=True)
class WorldSetup:
    """What a world holds before a scenario acts on it."""

    modules: int = MODULE_COUNT
    pack_files: int = PACK_FILE_COUNT
    pipeline_table: str = DEFAULT_PIPELINE_TABLE


@dataclass
class World:
    """One library a scenario acts on: its collection, its sample pack, its labels and its config.

    Every act reads and changes this world the way a person or another process would, so what a run
    sees is what the file system and the catalog actually hold. Every read ends its transaction, so
    the world never holds a lock a run's reset waits on.
    """

    root: Path
    database_url: str
    connection: Connection
    setup: WorldSetup
    labels: bool = field(default=False, init=False)
    labels_file_name: str = field(default="labels.jsonl", init=False)
    pipeline_table: str = field(default=DEFAULT_PIPELINE_TABLE, init=False)
    added_modules: int = field(default=0, init=False)
    added_pack_files: int = field(default=0, init=False)
    holders: dict[str, Connection] = field(default_factory=dict, init=False)

    @property
    def collection(self) -> Path:
        return self.root / "collection"

    @property
    def pack(self) -> Path:
        return self.root / "packs"

    @property
    def library_root(self) -> Path:
        return self.root / "library"

    @property
    def labels_file(self) -> Path:
        return self.root / self.labels_file_name

    @property
    def config(self) -> Path:
        return self.root / "config.toml"

    @property
    def layout(self) -> PipelineLayout:
        return PipelineLayout(library_root=self.library_root)

    def build(self) -> None:
        """Write the collection, the pack and the configuration this world starts from."""
        self.collection.mkdir(parents=True, exist_ok=True)
        self.pack.mkdir(parents=True, exist_ok=True)
        self.library_root.mkdir(parents=True, exist_ok=True)
        for name, data in list(sandbox_modules(self.setup.modules).items())[: self.setup.modules]:
            (self.collection / name).write_bytes(data)
        for relative_path, pack_file in list(sample_pack().items())[: self.setup.pack_files]:
            path = self.pack / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            soundfile.write(path, pack_file.waveform, pack_file.rate, subtype=pack_file.subtype)
        self.pipeline_table = self.setup.pipeline_table
        self.write_config()

    def write_config(self) -> None:
        """Write the configuration naming this world, with its labels file where it has one."""
        labels_line = f'labels = "{self.labels_file.as_posix()}"\n' if self.labels else ""
        self.config.write_text(
            "[library]\n"
            f'module_source_directory = "{self.collection.as_posix()}"\n'
            f'library_root = "{self.library_root.as_posix()}"\n'
            f'database_url = "{self.database_url}"\n'
            f'sample_directories = ["{self.pack.as_posix()}"]\n'
            "minimum_sample_frames = 16\n"
            "\n[pipeline]\n"
            f"{labels_line}{self.pipeline_table}",
            encoding="utf-8",
        )

    def set_pipeline_table(self, table: str) -> None:
        """Rewrite the pipeline table, as a person editing the configuration does."""
        self.pipeline_table = table
        self.write_config()

    def add_module(self) -> Path:
        """Put the next of the sandbox's modules in the collection, the way a person adding to it does."""
        self.added_modules += 1
        index = self.setup.modules + self.added_modules - 1
        name, data = list(sandbox_modules(index + 1).items())[index]
        path = self.collection / name
        path.write_bytes(data)
        return path

    def remove_module(self) -> Path:
        """Take the last module out of the collection."""
        path = sorted(self.collection.iterdir())[-1]
        path.unlink()
        return path

    def add_pack_file(self) -> Path:
        """Put another sample file in the pack, with a sound of its own."""
        self.added_pack_files += 1
        path = self.pack / "Added" / f"Tone {self.added_pack_files:02d}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        waveform = decaying(
            tonal_waveform(
                ADDED_PACK_FRAMES, frequency=90.0 + 7.0 * self.added_pack_files, seed=900 + self.added_pack_files
            ),
            rate=SAMPLE_RATE,
        )
        soundfile.write(path, waveform.reshape(-1, 1), SAMPLE_RATE, subtype="PCM_16")
        return path

    def pack_files(self) -> tuple[Path, ...]:
        return tuple(sorted(path for path in self.pack.rglob("*") if path.is_file()))

    def delete_pack_file(self) -> Path:
        """Take the last sample file out of the pack, as a deletion does."""
        path = self.pack_files()[-1]
        path.unlink()
        return path

    def touch_pack_file(self) -> Path:
        """Move a sample file's write time without changing a byte of it."""
        path = self.pack_files()[0]
        status = path.stat()
        os.utime(path, ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000_000))
        return path

    def unmount_the_pack(self) -> None:
        """Move the whole sample directory aside, which is what an unplugged drive leaves behind."""
        shutil.move(self.pack, self.root / "packs-aside")

    def remount_the_pack(self) -> None:
        """Put the sample directory back where the configuration names it."""
        shutil.move(self.root / "packs-aside", self.pack)

    def first_module_sample(self) -> tuple[str, SampleOccurrence, str]:
        """The hash, occurrence and module file name of a sample the first module holds."""
        module = sorted(PostgresModuleRepository(self.connection).list_all(), key=lambda held: held.filename)[0]
        occurrences = PostgresSamplePropertiesRepository(self.connection).list_for_module(module.hash)
        self.connection.rollback()
        first = sorted(occurrences, key=lambda held: (held.occurrence.instrument_index, held.occurrence.sample_slot))[0]
        return first.sample_hash, first.occurrence, module.filename

    def write_labels_file(self, label: str) -> Path:
        """Write a labels file naming a sample the first module holds, as an export of another library would."""
        sample_hash, occurrence, filename = self.first_module_sample()
        annotation = _annotation(sample_hash, occurrence, filename, label=label)
        self.labels_file.write_text(f"{annotation.model_dump_json()}\n", encoding="utf-8")
        self.labels = True
        self.write_config()
        return self.labels_file

    def label_a_sample(self, label: str, rating: int | None = None) -> None:
        """Write a label and a rating the way the application does, on a sample the first module holds."""
        sample_hash, occurrence, filename = self.first_module_sample()
        PostgresSampleAnnotationRepository(self.connection).upsert_many(
            (_annotation(sample_hash, occurrence, filename, label=label, rating=rating),)
        )
        self.connection.commit()

    def step_outputs(self, step: str) -> Mapping[str, str]:
        """What a step's last complete run produced, as its record names it."""
        record = read_step_record(self.layout.step_record(step))
        assert record is not None, f"{step} never completed"
        return record.outputs

    def hold_the_pipeline_lock(self) -> str:
        """Hold this library's pipeline lock from a connection of its own, as another run would."""
        return self._hold_a_lock("pipeline", pipeline_lock_name(self.context().library_identity))

    def hold_a_step_lock(self, step: str) -> str:
        """Hold one step's lock from a connection of its own, as that step's orphaned process would."""
        return self._hold_a_lock(step, self.context().scope_name(step))

    def hold_a_table(self, table: str) -> str:
        """Read a table in a transaction left open, as the application serving the library does between requests."""
        reader = connect(self.database_url, read_only=True)
        reader.execute(text(f'SELECT 1 FROM "{table}" LIMIT 1'))
        self.holders[f"reader of {table}"] = reader
        return f"reader of {table}"

    def end_the_pipeline_lock_session(self) -> None:
        """End the database session holding this library's pipeline lock, as a restarted server or a dropped connection does."""
        key = named_lock_key(pipeline_lock_name(self.context().library_identity)) & 0xFFFFFFFFFFFFFFFF
        ended = (
            self.connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' "
                    "AND classid = :classid AND objid = :objid AND objsubid = 1"
                ),
                {"classid": key >> 32, "objid": key & 0xFFFFFFFF},
            )
            .scalars()
            .all()
        )
        self.connection.commit()
        assert ended == [True], "no session held the pipeline lock"

    def move_labels_file(self, name: str) -> Path:
        """Move the labels file under another name and point the configuration at it."""
        moved = self.labels_file.rename(self.root / name)
        self.labels_file_name = name
        self.write_config()
        return moved

    def release(self, held: str) -> None:
        """Let go of a lock this world holds, as the process holding it ending would."""
        self.holders.pop(held).close()

    def _hold_a_lock(self, held: str, name: str) -> str:
        holder = connect(self.database_url, read_only=True)
        assert claim_named_lock(holder, name), f"{name} was already held"
        holder.commit()
        self.holders[held] = holder
        return held

    def context(self) -> PipelineContext:
        """What a step reads about this world, read the way `status` reads it."""
        return PipelineContext(
            config=load_config(self.config),
            settings=read_pipeline_settings(self.config),
            connection=self.connection,
            layout=self.layout,
        )

    def stray_locks(self) -> tuple[str, ...]:
        """The locks of this world some process holds, apart from the ones this world holds itself.

        A step's lock stands for its process still running, and the pipeline's for a run still going.
        """
        context = PipelineContext(
            config=load_config(self.config),
            settings=PipelineSettings(),
            connection=self.connection,
            layout=self.layout,
        )
        names = {
            name: context.scope_name(name) for name in (RESET_STEP, *(step.name for step in library_graph().steps))
        }
        names["pipeline"] = pipeline_lock_name(context.library_identity)
        held = tuple(
            name for name, lock in names.items() if name not in self.holders and step_is_running(self.connection, lock)
        )
        self.connection.commit()
        return held

    def catalog_digests(self) -> dict[str, str]:
        """What the catalog holds now, as digests a scenario compares between acts."""
        self.connection.rollback()
        completions = PostgresPassCompletionRepository(self.connection)
        digests = {
            "modules": PostgresModuleRepository(self.connection).membership_digest(),
            "samples": PostgresSampleRepository(self.connection).membership_digest(),
            "relations": PostgresSampleRelationRepository(self.connection).membership_digest(),
            "labels": PostgresSampleAnnotationRepository(self.connection).label_digest(),
            "files": digest_of_rows(
                sorted(
                    (cataloged.location.relative_path, cataloged.sample_hash)
                    for cataloged in PostgresSampleFileRepository(self.connection).list_all()
                )
            ),
            "passes": digest_of_rows(
                sorted(
                    (kind.value, completion.digest)
                    for kind in PassKind
                    if (completion := completions.get(kind)) is not None
                )
            ),
            "experiments": self._experiments_digest(),
            "categories": self._shown_digest(category_promotion.c.experiment_id),
            "cloud": digest_of_rows(
                [
                    (self._shown_digest(cloud_promotion.c.experiment_id),),
                    *sorted(
                        (row.sample_hash,) for row in PostgresCloudCoordinateRepository(self.connection).list_all()
                    ),
                ]
            ),
            "artifacts": self._artifacts_digest(),
        }
        self.connection.rollback()
        return digests

    def _artifacts_digest(self) -> str:
        """Every artifact the pipeline sealed under the library root, by its place and what it holds, and what is published.

        An evaluation report records when it was made, so it counts by its place alone.
        """
        sealed = sorted(
            (
                sidecar.relative_to(self.library_root).as_posix(),
                None if sidecar.is_relative_to(self.layout.evaluations) else read_sidecar_content(sidecar),
            )
            for sidecar in self.library_root.rglob(f"*{SIDECAR_SUFFIX}")
        )
        published = read_published(self.library_root)
        return digest_of_rows(
            [
                *sealed,
                ("published", None if published is None else published.codec.content),
                ("published", None if published is None else published.restorer.content),
            ]
        )

    def _experiments_digest(self) -> str:
        """Every experiment by its key and backend, with the samples it describes, its id aside."""
        vectors = PostgresSampleFeatureVectorRepository(self.connection)
        rows = self.connection.execute(
            select(experiment.c.id, experiment.c.key, experiment.c.backend_name).order_by(experiment.c.key)
        ).all()
        return digest_of_rows((row.key, row.backend_name, vectors.membership_digest(row.id)) for row in rows)

    def _shown_digest(self, promoted: Column[int]) -> str:
        """Which experiment a promotion table names as shown, by its key."""
        rows = self.connection.execute(
            select(experiment.c.key).join_from(promoted.table, experiment, experiment.c.id == promoted)
        ).all()
        return digest_of_rows(sorted((row.key,) for row in rows))

    def experiment_by_key(self, key: str) -> tuple[int, int] | None:
        """The id of the experiment under a key and how many vectors it holds, or nothing where none is filed."""
        filed = PostgresExperimentRepository(self.connection).get_by_key(key)
        held = (
            None
            if filed is None
            else (
                filed.id,
                len(PostgresSampleFeatureVectorRepository(self.connection).heard_rates_for_experiment(filed.id)),
            )
        )
        self.connection.rollback()
        return held

    def close(self) -> None:
        for held in list(self.holders):
            self.release(held)


def _annotation(
    sample_hash: str, occurrence: SampleOccurrence, filename: str, *, label: str, rating: int | None = None
) -> SampleAnnotation:
    return SampleAnnotation(
        sample_hash=sample_hash,
        label=label,
        rating=rating,
        favorite=False,
        anchor=ModuleSlotAnchor(occurrence=occurrence, module_filename=filename, sample_name="scenario"),
        source=AnnotationSource.SAMPLE,
        annotated_at=datetime.now(UTC),
    )


def read_sidecar_content(sidecar: Path) -> str:
    """What the artifact a sidecar describes held when it was sealed."""
    return ArtifactSidecar.model_validate_json(sidecar.read_text(encoding="utf-8")).content
