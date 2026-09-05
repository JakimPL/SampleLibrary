from __future__ import annotations

import sys

from samplecore.cli_support import load_config_or_exit
from samplecore.storage.database import connect
from sampleextract.run import run_extraction


def main() -> None:
    """Run one extraction pass over the configured module source directory and report the result."""
    config = load_config_or_exit()
    config.library_root.mkdir(parents=True, exist_ok=True)
    connection = connect(config.resolved_database_path)
    try:
        summary = run_extraction(config, connection)
    finally:
        connection.close()

    print(
        f"Discovered {summary.discovered} modules: {len(summary.ingested)} ingested, "
        f"{summary.skipped_existing} already known, {len(summary.failures)} failed."
    )
    for failure in summary.failures:
        print(f"  {failure.path}: {failure.reason}")

    if summary.failures:
        sys.exit(1)
