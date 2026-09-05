from __future__ import annotations

import io
import sys

from samplecore.config import ConfigurationError, LibraryConfig, load_config


def configure_console_output_encoding() -> None:
    """Let stdout and stderr substitute an escape for any character the console cannot encode.

    Shared by every console entry point in this project. A narrow console codepage (for example
    Windows' cp1250) cannot represent every character a catalogued module or sample path may
    contain; without this, printing such a path crashes the whole command instead of garbling
    only that one line. Left alone when a stream has been replaced by something other than the
    usual text wrapper, such as a test's captured stream.
    """
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(errors="backslashreplace")


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


def bootstrap_cli() -> LibraryConfig:
    """Prepare a console entry point to run, then load its configuration.

    Shared by every console entry point in this project, so setup is identical regardless of
    which one was run.

    Raises:
        SystemExit: the configuration file is missing or fails validation.
    """
    configure_console_output_encoding()
    return load_config_or_exit()
