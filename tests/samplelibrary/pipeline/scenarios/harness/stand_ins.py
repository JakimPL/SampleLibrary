from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from samplecore.cli_support import load_config_or_exit
from samplecore.exit_status import ExitStatus
from samplecore.storage.atomic import write_bytes_atomically

VECTOR_SIZE: Final[int] = 512
MIDWAY_CHECKPOINT_INTERVAL: Final[int] = 2
MIDWAY_EPOCH: Final[int] = 1
SEED_BYTES: Final[int] = 8
PROGRAM: Final[str] = "samplelibrary"
# The machine a command runs on names nothing it builds, and neither does the number the catalog
# happened to give an experiment, which a catalog rebuilt from nothing numbers again.
UNNAMING_WORDS: Final[frozenset[str]] = frozenset({"--workers", "--device", "--teacher-experiment"})
BEST_VALIDATION_LOSS: Final[float] = 0.5
PLANE_DIMENSIONS: Final[int] = 2

Gate = Callable[[], None]


@dataclass(frozen=True)
class StandIn:
    """How a stood-in command behaves this attempt: where it stops partway, and whether its bytes differ from the last."""

    midway: Gate | None
    varies: bool
    notes: Path

    def note(self, **entry: object) -> None:
        """Say something about what the stand-in did, for a scenario reading more than the pipeline reports."""
        with self.notes.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry) + "\n")


def _seeded(content: bytes) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(content).digest()[:SEED_BYTES], "little"))


def describe_frames(waveform: NDArray[np.float64]) -> NDArray[np.float64]:
    """A vector standing for a sample's frames alone, so the same frames give the same vector in any process."""
    return _seeded(np.ascontiguousarray(waveform, dtype=np.float32).tobytes()).standard_normal(VECTOR_SIZE)


class HeardContentExtractor:
    """Describes a sample by the frames it hears, standing in for a model that describes a sample the same way every time.

    It stops at the scenario's midway gate before the sample after the first checkpoint.
    """

    def __init__(self, midway: Gate | None) -> None:
        self._midway = midway
        self._described = 0

    def extract(self, waveform: NDArray[np.float64]) -> NDArray[np.float64]:
        self._described += 1
        if self._midway is not None and self._described == MIDWAY_CHECKPOINT_INTERVAL + 1:
            self._midway()
        return describe_frames(waveform)


class WordedTeacher:
    """Reads each prompt into a vector of its own words, standing in for a listening model's text tower."""

    def embed_text(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return np.stack([_seeded(text.encode("utf-8")).standard_normal(VECTOR_SIZE) for text in texts]).astype(
            np.float32
        )


def lay_out_on_a_plane(standardized: NDArray[np.float64], *, n_neighbors: int) -> NDArray[np.float64]:
    """A sample's first two standardized features as its place on the cloud, standing in for a fitted layout.

    The same vectors give the same places in any process and a changed vector moves its point, which
    is all a scenario reads of a layout; the slice is ready at once in each of the dozens of processes
    a scenario starts, where a fitted layout compiles its kernels anew in every one.
    """
    return standardized[:, :PLANE_DIMENSIONS]


def run_stand_in(command: Sequence[str], stand_in: StandIn) -> None:
    """Run a command whose model a scenario cannot load or train as the real command does, with the model stood in for.

    A command reading a model runs for real with the model replaced; a command training one writes
    what training leaves -- the model, a resume point each epoch, the finished record -- under the
    real paths; every other command a scripted step names does nothing of its own.
    """
    words = list(command)
    match tuple(words[:2]):
        case ("cloud", "embed"):
            _cloud_embed(words[2:], stand_in)
        case ("cloud", "categorize"):
            _categorize(words[2:])
        case ("cloud", "evaluate"):
            _evaluate(words[2:], stand_in)
        case ("descriptor", "cache-grids"):
            _cache_grids(words[2:], stand_in)
        case ("descriptor", "train"):
            _train_descriptor(words[2:], stand_in)
        case ("descriptor", "embed"):
            _embed_cache(words[2:])


# Each command below is imported only by the stand-in running it, so a scripted pass loads none of them.
# pylint: disable=import-outside-toplevel


def _cloud_embed(argv: list[str], stand_in: StandIn) -> None:
    import samplecloud.cli
    import samplecloud.features
    import samplecloud.reduce

    extractor = HeardContentExtractor(stand_in.midway)
    samplecloud.cli.extractor_for = lambda recipe, *, library_root, device: extractor  # type: ignore[assignment]
    samplecloud.reduce.fit_plane = lay_out_on_a_plane
    if stand_in.midway is not None:
        samplecloud.features.EXTRACTION_CHECKPOINT_INTERVAL = MIDWAY_CHECKPOINT_INTERVAL  # type: ignore[misc]
    samplecloud.cli.main(argv, prog=f"{PROGRAM} cloud embed")


def _categorize(argv: list[str]) -> None:
    import samplecloud.categories.cli

    samplecloud.categories.cli.load_teacher = lambda *, device: WordedTeacher()  # type: ignore[assignment]
    samplecloud.categories.cli.main(argv, prog=f"{PROGRAM} cloud categorize")


@contextmanager
def _silent_run(library_root: Path, *, recorded: bool, experiment_name: str, run_name: str) -> Iterator[object]:
    from samplecore.tracking.silent import SilentRun

    yield SilentRun()


def _evaluate(argv: list[str], stand_in: StandIn) -> None:
    import samplecloud.evaluation.cli

    extractor = HeardContentExtractor(stand_in.midway)
    samplecloud.evaluation.cli.extractor_for = lambda recipe, *, library_root, device: extractor  # type: ignore[assignment]
    samplecloud.evaluation.cli.open_run = _silent_run  # type: ignore[assignment]
    samplecloud.evaluation.cli.main(argv, prog=f"{PROGRAM} cloud evaluate")


def _descriptor_arguments(argv: list[str]) -> object:
    from sampledescriptor.cli import parse_arguments

    return parse_arguments(argv, prog=f"{PROGRAM} descriptor")


def _content(argv: list[str], stand_in: StandIn) -> bytes:
    """The bytes a stood-in model holds: what its command asked for, and something new each attempt where it varies.

    The machine a command runs on, the catalog's numbering and whether it resumes stay out of them,
    as they stay out of what a real training run converges to.
    """
    asked = [
        word for index, word in enumerate(argv) if word not in UNNAMING_WORDS and argv[index - 1] not in UNNAMING_WORDS
    ]
    nonce = os.urandom(SEED_BYTES) if stand_in.varies else b""
    return hashlib.sha256(json.dumps([word for word in asked if word != "--resume"]).encode("utf-8") + nonce).digest()


def _cache_grids(argv: list[str], stand_in: StandIn) -> None:
    from samplecore.storage.database import connect
    from samplecore.storage.sample_audio import readable_sample_hashes
    from sampledescriptor.commands.cache_grids import COMMAND_NAME
    from sampledescriptor.training.cache_staging import STAGING_SUFFIX
    from sampledescriptor.training.descriptor.cache import (
        DESCRIPTION_FILE_NAME,
        GRIDS_FILE_NAME,
        HASHES_FILE_NAME,
        grid_cache_directory,
    )

    arguments = _descriptor_arguments([COMMAND_NAME, *argv])
    config = load_config_or_exit()
    with connect(config.database_url) as connection:
        hashes = sorted(readable_sample_hashes(connection))
    directory = grid_cache_directory(config.library_root, name=arguments.cache)  # type: ignore[attr-defined]
    staging = directory.with_name(directory.name + STAGING_SUFFIX)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    grids = _seeded(_content(argv, stand_in)).standard_normal((len(hashes), 4, 4)).astype(np.float32)
    np.save(staging / GRIDS_FILE_NAME, grids)
    (staging / HASHES_FILE_NAME).write_text("\n".join(hashes), encoding="utf-8")
    (staging / DESCRIPTION_FILE_NAME).write_text(json.dumps({"samples": len(hashes)}), encoding="utf-8")
    shutil.rmtree(directory, ignore_errors=True)
    staging.replace(directory)


def _train_descriptor(argv: list[str], stand_in: StandIn) -> None:
    from sampledescriptor.commands.train_descriptor import COMMAND_NAME
    from sampledescriptor.model_paths import descriptor_path
    from sampledescriptor.training.run.paths import RunFamily

    arguments = _descriptor_arguments([COMMAND_NAME, *argv])
    root = load_config_or_exit().library_root
    name = arguments.descriptor  # type: ignore[attr-defined]
    _train(arguments, argv, stand_in, family=RunFamily.DESCRIPTOR, name=name, model=descriptor_path(root, name=name))


def _train(arguments: object, argv: list[str], stand_in: StandIn, *, family: object, name: str, model: Path) -> None:
    """Leave what a training run leaves: the best model after every epoch, a resume point, and the finished record last."""
    from sampledescriptor.training.run.paths import RunFinished, finished_record_path, resume_path

    root = load_config_or_exit().library_root
    resume = resume_path(root, family=family, name=name)  # type: ignore[arg-type]
    finished = finished_record_path(root, family=family, name=name)  # type: ignore[arg-type]
    resuming = bool(arguments.resume)  # type: ignore[attr-defined]
    if resuming and not resume.is_file():
        print(f"Trained nothing: --resume continues from {resume}, and no run of that name stopped there.")
        sys.exit(ExitStatus.REFUSED)
    start = int(json.loads(resume.read_text(encoding="utf-8"))["epoch"]) if resuming else 0
    if not resuming:
        finished.unlink(missing_ok=True)
    stand_in.note(trained=name, resumed_from=start)
    content = _content(argv, stand_in)
    epochs = int(arguments.epochs)  # type: ignore[attr-defined]
    for epoch in range(start, epochs):
        write_bytes_atomically(model, content + epoch.to_bytes(4, "little"))
        write_bytes_atomically(resume, json.dumps({"epoch": epoch + 1}).encode("utf-8"))
        if stand_in.midway is not None and epoch + 1 == MIDWAY_EPOCH:
            stand_in.midway()
    record = RunFinished(epochs_completed=epochs, best_validation_loss=BEST_VALIDATION_LOSS)
    write_bytes_atomically(finished, record.model_dump_json().encode("utf-8"))


def _embed_cache(argv: list[str]) -> None:
    """File an experiment of every cached sample's vector in one transaction, the way a descriptor's embedding lands."""
    from samplecore.models.experiment import (
        LEARNED_BACKEND_NAME,
        MODEL_PARAMETER,
        READING_PARAMETER,
        Reading,
        SampleFeatureVector,
    )
    from samplecore.storage.database import connect, start_batch
    from samplecore.storage.repositories.experiment import PostgresExperimentRepository
    from samplecore.storage.repositories.feature_vector import PostgresSampleFeatureVectorRepository
    from samplecore.storage.sample_audio import SampleAudio
    from sampledescriptor.commands.embed import COMMAND_NAME
    from sampledescriptor.model_paths import descriptor_path
    from sampledescriptor.training.descriptor.cache import HASHES_FILE_NAME, grid_cache_directory

    arguments = _descriptor_arguments([COMMAND_NAME, *argv])
    config = load_config_or_exit()
    descriptor = descriptor_path(config.library_root, name=arguments.descriptor)  # type: ignore[attr-defined]
    if not descriptor.is_file():
        print(f"No descriptor is stored at {descriptor}.")
        sys.exit(ExitStatus.FAILED)
    cache = grid_cache_directory(config.library_root, name=arguments.cache)  # type: ignore[attr-defined]
    hashes = (cache / HASHES_FILE_NAME).read_text(encoding="utf-8").split("\n")
    with connect(config.database_url) as connection:
        experiments = PostgresExperimentRepository(connection)
        if experiments.get_by_key(arguments.key) is not None:  # type: ignore[attr-defined]
            return
        audio = SampleAudio.from_catalog(connection, config.library_root)
        now = datetime.now(UTC)
        with start_batch(connection):
            experiment_id = experiments.insert_new(
                backend_name=LEARNED_BACKEND_NAME,
                label=None,
                params={MODEL_PARAMETER: descriptor.stem, READING_PARAMETER: Reading.NOMINAL.value},
                key=arguments.key,  # type: ignore[attr-defined]
            )
            PostgresSampleFeatureVectorRepository(connection).insert_many(
                [
                    SampleFeatureVector(
                        experiment_id=experiment_id,
                        sample_hash=sample_hash,
                        vector=tuple(float(value) for value in describe_frames(audio.read_by_hash(sample_hash).pcm)),
                        computed_at=now,
                    )
                    for sample_hash in hashes
                ]
            )
