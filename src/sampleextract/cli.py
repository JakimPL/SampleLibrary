from __future__ import annotations

import sys

from samplecore.config import ConfigurationError, load_config
from samplecore.storage.database import connect
from sampleextract.run import run_extraction


def main() -> None:
    """Run one extraction pass over the configured module source directory and report the result."""
    try:
        config = load_config()
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        sys.exit(1)

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
