from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Final

from samplelibrary.sandbox.modules import TARGET_MODULE_COUNT, sandbox_modules
from samplelibrary.sandbox.sample_pack import SAMPLE_PACK_EXCLUSIONS, write_sample_pack

DEFAULT_OUTPUT_DIRECTORY: Final[Path] = Path("dev-library")
MODULES_DIRECTORY_NAME: Final[str] = "modules"
CATALOG_DIRECTORY_NAME: Final[str] = "catalog"
SAMPLE_PACK_DIRECTORY_NAME: Final[str] = "samples"
SANDBOX_INFERENCE_URL: Final[str] = "http://127.0.0.1:8011"


def _write_config(
    output_directory: Path,
    *,
    modules_directory: Path,
    catalog_directory: Path,
    sample_pack_directory: Path,
    database_url: str,
) -> None:
    config_path = output_directory / "config.toml"
    exclusions = ", ".join(_toml_string(pattern) for pattern in SAMPLE_PACK_EXCLUSIONS)
    config_path.write_text(
        "[library]\n"
        f"module_source_directory = {_toml_string(modules_directory.resolve().as_posix())}\n"
        f"library_root = {_toml_string(catalog_directory.resolve().as_posix())}\n"
        f"database_url = {_toml_string(database_url)}\n"
        f"sample_directories = [{_toml_string(sample_pack_directory.resolve().as_posix())}]\n"
        f"sample_exclusions = [{exclusions}]\n"
        "\n"
        "[inference]\n"
        f"url = {_toml_string(SANDBOX_INFERENCE_URL)}\n",
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

    ``modules_directory`` and ``sample_pack_directory`` are wiped and rewritten every call, so this
    stays safe to rerun whenever the scenarios change; ``catalog_directory`` is left untouched, since
    a developer may still want the catalog a prior extraction run built from it.
    """
    modules_directory = output_directory / MODULES_DIRECTORY_NAME
    catalog_directory = output_directory / CATALOG_DIRECTORY_NAME
    sample_pack_directory = output_directory / SAMPLE_PACK_DIRECTORY_NAME
    for rewritten in (modules_directory, sample_pack_directory):
        if rewritten.is_dir():
            shutil.rmtree(rewritten)
    modules_directory.mkdir(parents=True)
    catalog_directory.mkdir(parents=True, exist_ok=True)
    write_sample_pack(sample_pack_directory)

    written_paths: list[Path] = []
    for filename, data in sandbox_modules(target_module_count).items():
        path = modules_directory / filename
        path.write_bytes(data)
        written_paths.append(path)

    _write_config(
        output_directory,
        modules_directory=modules_directory,
        catalog_directory=catalog_directory,
        sample_pack_directory=sample_pack_directory,
        database_url=database_url,
    )
    return tuple(written_paths)
