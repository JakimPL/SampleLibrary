from __future__ import annotations

import sys

from samplecore.config import ConfigurationError, LibraryConfig, load_config


def load_config_or_exit() -> LibraryConfig:
    """Load the library configuration, exiting with a clear message when it cannot be found.

    Shared by every console entry point in this project, so a missing or invalid ``config.toml``
    is reported identically regardless of which one was run.

    Raises:
        SystemExit: the configuration file is missing or fails validation.
    """
    try:
        return load_config()
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        sys.exit(1)
