from __future__ import annotations

import argparse
from pathlib import Path

from samplecore.cli_support import load_config_or_exit
from samplecore.storage.cluster.provisioning import development_database_url
from samplelibrary.sandbox.build import DEFAULT_OUTPUT_DIRECTORY, build_sandbox
from samplelibrary.sandbox.modules import TARGET_MODULE_COUNT
from samplelibrary.sandbox.sample_pack import sample_pack


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a small, deterministic tracker-module corpus for fast local development, "
        "deliberately covering every equivalence-detection relation type."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_DIRECTORY, help="Where to write the corpus and its config.toml."
    )
    parser.add_argument(
        "--target-module-count",
        type=int,
        default=TARGET_MODULE_COUNT,
        help="Total module count to reach by topping up the deliberate scenarios with unrelated filler modules.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Build the sandbox beside the configured library, on the same server under the sandbox's own database."""
    arguments = _parse_arguments(argv)
    database_url = development_database_url(load_config_or_exit().catalog_url())
    written_paths = build_sandbox(
        arguments.output, database_url=database_url, target_module_count=arguments.target_module_count
    )
    print(
        f"Wrote {len(written_paths)} modules, {len(sample_pack())} sample files and config.toml "
        f"under {arguments.output.resolve()}"
    )


if __name__ == "__main__":
    main()
