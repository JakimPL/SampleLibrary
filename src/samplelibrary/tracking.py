from __future__ import annotations

import argparse

from samplecore.cli_support import bootstrap_cli
from samplecore.tracking.store import tracking_uri


def main(argv: list[str], *, prog: str) -> None:
    """Print where the configured library's runs are recorded, for `mlflow ui --backend-store-uri`."""
    _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    print(tracking_uri(config.library_root))


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog, description="Print the URI of the run store beside the configured library."
    )
    return parser.parse_args(argv)
