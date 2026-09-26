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
from samplelibrary.app.console import log_without_console
from samplelibrary.app.frontend import bundled_frontend
from samplelibrary.app.installation import PortHolder, close_running, port_holder
from samplelibrary.app.launcher import Launcher
from samplelibrary.app.processes import samplelibrary_command
from sampleserver.frontend import built_frontend

DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8000
BROWSER_DELAY_SECONDS: Final[float] = 0.5
INSTANCE_PROBE_SECONDS: Final[float] = 2.0
QUIT_WAIT_SECONDS: Final[float] = 180.0
RENDERER_COMMAND: Final[tuple[str, ...]] = ("morph", "serve")
PIPELINE_COMMAND: Final[tuple[str, ...]] = ("pipeline", "run")
DEVICE_COMMAND: Final[tuple[str, ...]] = ("device",)

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run the application: the library, everything it needs, and the pages that set it up, opened in a browser.

    A second start of the same installation while it runs opens the browser on the running one. A
    start of another installation, a new version or the other launcher, closes the running one and
    takes its place. A windowless start, which Windows gives the packaged application, writes its
    output to a log file, which it takes over once any other installation has closed.

    Raises:
        SystemExit: another program holds the port the application listens on, or the installation
            running on it stayed open.
    """
    arguments = _parse_arguments(argv, prog=prog)
    configure_console_output_encoding()
    configure_logging()
    address = f"http://{_browser_host(arguments.host)}:{arguments.port}/"
    with httpx.Client(base_url=f"{address.rstrip('/')}{SETUP_PREFIX}", timeout=INSTANCE_PROBE_SECONDS) as setup:
        holder = port_holder(setup)
        if holder is PortHolder.THIS_INSTALLATION:
            _logger.info("SampleLibrary is already running at %s. Opening it.", address)
            _open_browser(address, enabled=arguments.open_browser)
            return
        port_free = _free_port(setup, holder, address=address)
    if log_without_console() is not None:
        configure_logging()
    if not port_free:
        _logger.error("Port %d is in use. Quit the program using it, or try another port with --port.", arguments.port)
        sys.exit(ExitStatus.REFUSED)
    _serve(
        address=address,
        host=arguments.host,
        port=arguments.port,
        frontend=arguments.frontend or bundled_frontend(),
        open_browser=arguments.open_browser,
    )


def _free_port(setup: httpx.Client, holder: PortHolder, *, address: str) -> bool:
    """Whether the port is free for this start, closing another installation of the application running on it."""
    match holder:
        case PortHolder.NOBODY:
            return True
        case PortHolder.OTHER_INSTALLATION:
            _logger.info("SampleLibrary from another installation is running at %s. Closing it.", address)
            return close_running(setup, wait_seconds=QUIT_WAIT_SECONDS)
        case PortHolder.THIS_INSTALLATION | PortHolder.OTHER_PROGRAM:
            return False


def _serve(*, address: str, host: str, port: int, frontend: Path | None, open_browser: bool) -> None:
    """Serve the application until a person quits it, opening the browser on it once it answers."""
    launcher = Launcher(
        resolve_config_path(),
        renderer_command=samplelibrary_command(*RENDERER_COMMAND),
        pipeline_command=samplelibrary_command(*PIPELINE_COMMAND),
        device_command=samplelibrary_command(*DEVICE_COMMAND),
    )
    if frontend is None:
        _logger.warning("No built frontend found. Run `just frontend-build` first.")

    def schedule_browser() -> None:
        asyncio.get_running_loop().call_later(BROWSER_DELAY_SECONDS, _open_browser, address, open_browser)

    application = create_application(launcher, frontend_directory=frontend, on_ready=schedule_browser)
    server = uvicorn.Server(uvicorn.Config(application, host=host, port=port))
    application.state.request_quit = lambda: setattr(server, "should_exit", True)
    _logger.info("SampleLibrary is running at %s. Press Ctrl+C or click Quit to stop it.", address)
    server.run()


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
