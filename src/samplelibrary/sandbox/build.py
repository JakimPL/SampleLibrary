from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import soundfile

from samplecore.models.annotation import AnnotationSource, SampleAnnotation, SampleFileAnchor
from samplecore.models.sample_file import SampleFileLocation
from samplecore.sample_files.decoding import decode_sample_file
from samplelibrary.sandbox.modules import TARGET_MODULE_COUNT, sandbox_modules
from samplelibrary.sandbox.one_shots import labeled_one_shots, one_shots
from samplelibrary.sandbox.sample_pack import SAMPLE_PACK_EXCLUSIONS, write_sample_pack

DEFAULT_OUTPUT_DIRECTORY: Final[Path] = Path("dev-library")
MODULES_DIRECTORY_NAME: Final[str] = "modules"
CATALOG_DIRECTORY_NAME: Final[str] = "catalog"
SAMPLE_PACK_DIRECTORY_NAME: Final[str] = "samples"
SANDBOX_INFERENCE_URL: Final[str] = "http://127.0.0.1:8011"
LABELS_FILE_NAME: Final[str] = "labels.jsonl"
LABELED_AT: Final[datetime] = datetime(2026, 1, 1, tzinfo=UTC)
# A sandbox a few hundred samples large trains and fits in minutes, so its models are small and
# its training runs short.
SANDBOX_PIPELINE_TABLES: Final[str] = (
    'memory_cap = "none"\n'
    "\n[pipeline.descriptor]\nepochs = 4\nlabeled_per_batch = 8\n"
    "\n[pipeline.restorer]\nepochs = 2\n"
    "\n[pipeline.morph-codec]\nlatent_size = 32\n"
    "\n[pipeline.evaluation]\nprobes = 50\n"
    "\n[pipeline.module-evaluation]\nprobes = 50\n"
)


@dataclass(frozen=True)
class SandboxPaths:
    """Where one sandbox keeps its modules, its catalog, its sample pack and its labels file."""

    output: Path

    @property
    def modules(self) -> Path:
        return self.output / MODULES_DIRECTORY_NAME

    @property
    def catalog(self) -> Path:
        return self.output / CATALOG_DIRECTORY_NAME

    @property
    def sample_pack(self) -> Path:
        return self.output / SAMPLE_PACK_DIRECTORY_NAME

    @property
    def labels(self) -> Path:
        return self.output / LABELS_FILE_NAME


def _write_config(paths: SandboxPaths, *, database_url: str) -> None:
    config_path = paths.output / "config.toml"
    exclusions = ", ".join(_toml_string(pattern) for pattern in SAMPLE_PACK_EXCLUSIONS)
    config_path.write_text(
        "[library]\n"
        f"module_source_directory = {_toml_string(paths.modules.resolve().as_posix())}\n"
        f"library_root = {_toml_string(paths.catalog.resolve().as_posix())}\n"
        f"database_url = {_toml_string(database_url)}\n"
        f"sample_directories = [{_toml_string(paths.sample_pack.resolve().as_posix())}]\n"
        f"sample_exclusions = [{exclusions}]\n"
        "\n"
        "[inference]\n"
        f"url = {_toml_string(SANDBOX_INFERENCE_URL)}\n"
        "\n"
        "[pipeline]\n"
        f"labels = {_toml_string(paths.labels.resolve().as_posix())}\n"
        f"{SANDBOX_PIPELINE_TABLES}",
        encoding="utf-8",
    )


def _toml_string(value: str) -> str:
    """A value written as a TOML basic string, whose escapes JSON's own string escapes are a subset of."""
    return json.dumps(value)


def build_sandbox(
    output_directory: Path, *, database_url: str, target_module_count: int = TARGET_MODULE_COUNT
) -> tuple[Path, ...]:
    """(Re)generates the deterministic dev-module corpus and its own ready-to-use ``config.toml``.

    The config names ``database_url`` and an inference address of the sandbox's own, so passing it
    with `--config` points every command at the sandbox alone.

    The sample pack holds a few hundred one-shots, a labels file names one of every kind, and the
    pipeline table keeps the models small, so `samplelibrary pipeline run` builds the whole sandbox.

    The modules and the sample pack are written afresh every call, so this stays safe to rerun
    whenever the scenarios change; the catalog directory keeps whatever an earlier run built in it.
    """
    paths = SandboxPaths(output=output_directory)
    for rewritten in (paths.modules, paths.sample_pack):
        if rewritten.is_dir():
            shutil.rmtree(rewritten)
    paths.modules.mkdir(parents=True)
    paths.catalog.mkdir(parents=True, exist_ok=True)
    write_sample_pack(paths.sample_pack)
    _write_one_shots(paths.sample_pack)
    _write_labels(paths.labels, paths.sample_pack)

    written_paths: list[Path] = []
    for filename, data in sandbox_modules(target_module_count).items():
        path = paths.modules / filename
        path.write_bytes(data)
        written_paths.append(path)

    _write_config(paths, database_url=database_url)
    return tuple(written_paths)


def _write_one_shots(sample_pack_directory: Path) -> None:
    for relative_path, shot in one_shots().items():
        path = sample_pack_directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        soundfile.write(path, shot.waveform, shot.rate, subtype=shot.subtype)


def _write_labels(path: Path, sample_pack_directory: Path) -> None:
    """Write a label for one one-shot of every kind, as an export of a labeled library would hold them."""
    annotations = [
        SampleAnnotation(
            sample_hash=decode_sample_file(sample_pack_directory / relative_path).sample_pcm.sample.hash,
            label=label,
            rating=None,
            favorite=False,
            anchor=SampleFileAnchor(
                location=SampleFileLocation(directory=sample_pack_directory.resolve(), relative_path=relative_path)
            ),
            source=AnnotationSource.SAMPLE,
            annotated_at=LABELED_AT,
        )
        for relative_path, label in labeled_one_shots().items()
    ]
    path.write_text("".join(f"{annotation.model_dump_json()}\n" for annotation in annotations), encoding="utf-8")
