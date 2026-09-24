from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import webbrowser
from pathlib import Path
from typing import Final

import httpx
import uvicorn

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import configure_console_output_encoding, configure_logging, port_number
from samplecore.config import resolve_config_path
from samplecore.exit_status import ExitStatus
from samplelibrary.app.asgi import SETUP_PREFIX, create_application
from samplelibrary.app.frontend import bundled_frontend
from samplelibrary.app.launcher import Launcher
from samplelibrary.app.processes import samplelibrary_command
from sampleserver.frontend import built_frontend

DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8000
BROWSER_DELAY_SECONDS: Final[float] = 0.5
INSTANCE_PROBE_SECONDS: Final[float] = 2.0
RENDERER_COMMAND: Final[tuple[str, ...]] = ("morph", "serve")
PIPELINE_COMMAND: Final[tuple[str, ...]] = ("pipeline", "run")

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run the application: the library, everything it needs, and the pages that set it up, opened in a browser.

    A second start while the application already runs opens the browser on the running one.

    Raises:
        SystemExit: another program holds the port the application listens on.
    """
    arguments = _parse_arguments(argv, prog=prog)
    configure_console_output_encoding()
    configure_logging()
    address = f"http://{_browser_host(arguments.host)}:{arguments.port}/"
    match _running_instance(address):
        case True:
            _logger.info("SampleLibrary already runs at %s; opening it.", address)
            _open_browser(address, enabled=arguments.open_browser)
            return
        case None:
            _logger.error("Another program listens on port %d; start SampleLibrary with --port.", arguments.port)
            sys.exit(ExitStatus.REFUSED)
        case False:
            pass

    launcher = Launcher(
        resolve_config_path(),
        renderer_command=samplelibrary_command(*RENDERER_COMMAND),
        pipeline_command=samplelibrary_command(*PIPELINE_COMMAND),
    )
    frontend = arguments.frontend or bundled_frontend()
    if frontend is None:
        _logger.warning("No built frontend found; serving the API alone. `just frontend-build` builds one.")

    def schedule_browser() -> None:
        asyncio.get_running_loop().call_later(BROWSER_DELAY_SECONDS, _open_browser, address, arguments.open_browser)

    application = create_application(launcher, frontend_directory=frontend, on_ready=schedule_browser)
    server = uvicorn.Server(uvicorn.Config(application, host=arguments.host, port=arguments.port))
    application.state.request_quit = lambda: setattr(server, "should_exit", True)
    _logger.info("SampleLibrary runs at %s; close it with Ctrl+C or Quit in its menu.", address)
    server.run()


def _running_instance(address: str) -> bool | None:
    """Whether this application already answers at ``address``: yes, no one listens, or another program does."""
    try:
        response = httpx.get(f"{address.rstrip('/')}{SETUP_PREFIX}/state", timeout=INSTANCE_PROBE_SECONDS)
    except httpx.ConnectError:
        return False
    except httpx.HTTPError:
        return None
    return True if response.is_success else None


def _open_browser(address: str, enabled: bool) -> None:
    if enabled:
        webbrowser.open(address)


def _browser_host(host: str) -> str:
    """The host a browser on this machine reaches the application at, which is the loopback address for a wildcard bind."""
    return DEFAULT_HOST if host in ("0.0.0.0", "::") else host


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Run SampleLibrary with its setup pages, opened in a browser.")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="The address to bind.")
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT, help="The port to bind.")
    parser.add_argument(
        "--frontend",
        type=_frontend_directory,
        default=None,
        help="A built frontend to serve instead of the bundled one.",
    )
    parser.add_argument(
        "--browser",
        dest="open_browser",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open the application in the default browser on start.",
    )
    return parser.parse_args(argv)


def _frontend_directory(raw_value: str) -> Path:
    try:
        return built_frontend(Path(raw_value))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
