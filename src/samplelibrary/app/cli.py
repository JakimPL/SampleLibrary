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
from samplecore.ports import PortUnavailableError, listen_on_first_free
from samplelibrary.app.asgi import SETUP_PREFIX, create_application
from samplelibrary.app.console import console_log
from samplelibrary.app.frontend import bundled_frontend
from samplelibrary.app.instance.lock import LockUnavailableError
from samplelibrary.app.instance.place import InstancePlace, instance_place
from samplelibrary.app.instance.processes import current_process
from samplelibrary.app.instance.record import InstanceRecord, read_record, write_record
from samplelibrary.app.instance.system import HttpContact, SystemClock, SystemProcesses
from samplelibrary.app.instance.takeover import Claimed, Intent, Patience, Refused, Running, Takeover
from samplelibrary.app.launcher import Launcher
from samplelibrary.app.listener import LOOPBACK_HOST, port_choices
from samplelibrary.app.processes import samplelibrary_command
from sampleserver.frontend import built_frontend

BROWSER_DELAY_SECONDS: Final[float] = 0.5
PROBE_TIMEOUT: Final[httpx.Timeout] = httpx.Timeout(3.0, connect=1.0)
PATIENCE: Final[Patience] = Patience(poll=0.25, record=10.0, silent=20.0, quit=120.0, end_grace=10.0, release=10.0)
RENDERER_COMMAND: Final[tuple[str, ...]] = ("morph", "serve")
PIPELINE_COMMAND: Final[tuple[str, ...]] = ("pipeline", "run")
DEVICE_COMMAND: Final[tuple[str, ...]] = ("device",)

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Run the application: the library, everything it needs, and the pages that set it up, opened in a browser.

    One application runs under each config. A start finding the same installation running opens
    the browser on it; a start of another installation, a new version or the other launcher, asks
    the running one to quit and takes its place, and so does a start finding one that stopped
    answering, after ending it. `--quit` ends the running one the same way and starts nothing.

    Raises:
        SystemExit: the application running under this config stayed where it was, the state folder
            cannot hold a lock, or the port a person asked for is taken.
    """
    arguments = _parse_arguments(argv, prog=prog)
    configure_console_output_encoding()
    configure_logging()
    config_path = resolve_config_path()
    place = instance_place(config_path)
    takeover = Takeover(
        place,
        patience=PATIENCE,
        processes=SystemProcesses(),
        contact=HttpContact(setup_prefix=SETUP_PREFIX, timeout=PROBE_TIMEOUT),
        clock=SystemClock(),
    )
    try:
        claim = takeover.claim(Intent.QUIT if arguments.quit else Intent.START)
    except LockUnavailableError as error:
        _logger.error("%s", error)
        sys.exit(ExitStatus.REFUSED)
    match claim:
        case Refused(reason=reason):
            _logger.error("%s", reason)
            sys.exit(ExitStatus.REFUSED)
        case Running(address=address):
            _logger.info("SampleLibrary is already running at %s. Opening it.", address)
            _open_browser(address, enabled=arguments.open_browser)
        case Claimed(lock=lock):
            with lock:
                if arguments.quit:
                    _logger.info("SampleLibrary is closed.")
                    return
                _serve(
                    place,
                    config_path=config_path,
                    requested_port=arguments.port,
                    frontend=arguments.frontend or bundled_frontend(),
                    open_browser=arguments.open_browser,
                )


def _serve(
    place: InstancePlace, *, config_path: Path, requested_port: int | None, frontend: Path | None, open_browser: bool
) -> None:
    """Serve the application from its place until a person quits it, opening the browser on it once it answers.

    The application listens before anything else starts, and records where right away, so a start
    arriving meanwhile finds it at once and waits in the queue of its port while it gets ready.

    Raises:
        SystemExit: the port a person asked for is taken.
    """
    with console_log(place.log, previous=place.previous_log) as log:
        if log is not None:
            configure_logging()
        try:
            listener = listen_on_first_free(LOOPBACK_HOST, port_choices(requested_port, read_record(place.record)))
        except PortUnavailableError as error:
            _logger.error("%s Leave --port out to let SampleLibrary choose a port.", error)
            sys.exit(ExitStatus.REFUSED)
        port: int = listener.getsockname()[1]
        write_record(place.record, InstanceRecord(host=LOOPBACK_HOST, port=port, process=current_process()))
        address = f"http://{LOOPBACK_HOST}:{port}/"
        launcher = Launcher(
            config_path,
            renderer_command=samplelibrary_command(*RENDERER_COMMAND),
            pipeline_command=samplelibrary_command(*PIPELINE_COMMAND),
            device_command=samplelibrary_command(*DEVICE_COMMAND),
        )
        if frontend is None:
            _logger.warning("No built frontend found. Run `just frontend-build` first.")

        def schedule_browser() -> None:
            asyncio.get_running_loop().call_later(BROWSER_DELAY_SECONDS, _open_browser, address, open_browser)

        application = create_application(launcher, frontend_directory=frontend, on_ready=schedule_browser)
        server = uvicorn.Server(uvicorn.Config(application, proxy_headers=False))
        application.state.request_quit = lambda: setattr(server, "should_exit", True)
        _logger.info("SampleLibrary is running at %s. Press Ctrl+C or click Quit to stop it.", address)
        server.run(sockets=[listener])


def _open_browser(address: str, enabled: bool) -> None:
    if enabled:
        webbrowser.open(address)


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Run SampleLibrary with its setup pages, opened in a browser.")
    parser.add_argument(
        "--port",
        type=port_number,
        default=None,
        help="The port to listen on. Left out, SampleLibrary keeps the port it listened on last, or finds a free one.",
    )
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
    parser.add_argument(
        "--quit",
        action="store_true",
        help="Quit the SampleLibrary running under this config, and wait until it has ended.",
    )
    return parser.parse_args(argv)


def _frontend_directory(raw_value: str) -> Path:
    try:
        return built_frontend(Path(raw_value))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
