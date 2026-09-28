from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from dataclasses import dataclass, field
from typing import Final

from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli
from samplecore.config import resolve_config_path
from samplecore.exit_status import ExitStatus
from sampleripper.children import ChildProcess
from sampleripper.site.admission import SiteRefusedError, admit_site, site_port, site_warnings
from sampleripper.site.messages import RENDERER_ENDED
from sampleripper.site.renderer import RendererDidNotStartError, site_renderer, wait_until_answering
from sampleserver.cli import WORKER_COUNT_ENVIRONMENT_VARIABLE, admit_reader, names_a_process_count, run_server

DEFAULT_SITE_HOST: Final[str] = "0.0.0.0"

_logger = logging.getLogger(__name__)


@dataclass
class _RendererWatch:
    """Whether the renderer ended while the site served, which the watching thread notes before stopping the site.

    ``stopping`` is set once the site stops on its own, so the renderer it stops then is not taken
    for one that failed.
    """

    stopping: threading.Event = field(default_factory=threading.Event)
    ended_with: list[int] = field(default_factory=list)


def main(argv: list[str], *, prog: str) -> None:
    """Serve the library to anyone, as a site: the catalog's API and pages, and the morph renderer beside them.

    Everything a site may not do is refused before anything starts (`sampleripper.site.admission`),
    and the reader's role is checked the way `sampleripper serve` checks it. A site without its audio
    yet starts and says so, since a platform's volume is filled through the running site
    (`site_warnings`). The renderer runs as a child on the loopback address, and the site serves once it answers. A renderer that ends while
    the site serves ends the site with status 1, so the platform running it starts both again; a site
    stopping stops its renderer.

    Raises:
        SystemExit: the site may not start as configured (3), the renderer failed (1).
    """
    arguments = _parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    try:
        port = site_port(os.environ)
        admit_site(config, port=port, environment=os.environ)
    except SiteRefusedError as refusal:
        for problem in refusal.problems:
            _logger.error("%s", problem)
        sys.exit(ExitStatus.REFUSED)
    admit_reader(config)
    for warning in site_warnings(config):
        _logger.warning("%s", warning)

    renderer = site_renderer(config.inference, environment=os.environ, config_path=resolve_config_path())
    renderer.start()
    watch = _RendererWatch()
    try:
        wait_until_answering(renderer, config.inference)
        threading.Thread(target=_stop_the_site_when_it_ends, args=(renderer, watch), daemon=True).start()
        run_server(host=arguments.host, port=port, reload=False, workers=None)
    except RendererDidNotStartError as error:
        _logger.error("%s", error)
        sys.exit(ExitStatus.FAILED)
    finally:
        watch.stopping.set()
        renderer.stop()
    if watch.ended_with:
        sys.exit(ExitStatus.FAILED)


def _stop_the_site_when_it_ends(renderer: ChildProcess, watch: _RendererWatch) -> None:
    """Wait for the renderer to end, then stop the server."""
    status = renderer.wait()
    if watch.stopping.is_set():
        return
    watch.ended_with.append(status)
    _logger.error("%s", RENDERER_ENDED.format(status=status))
    stop_the_server()


def stop_the_server() -> None:
    """Stop the server this process runs the way the platform stops it, which ends it as a stop from outside does."""
    os.kill(os.getpid(), signal.SIGTERM)


def _parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(
        prog=prog,
        description="Serve the library to anyone as a site, with its morph renderer. It listens on the port $PORT names.",
    )
    parser.add_argument(
        "--host", type=str, default=DEFAULT_SITE_HOST, help="The address to listen on; every address by default."
    )
    arguments = parser.parse_args(argv)
    if not names_a_process_count(os.environ.get(WORKER_COUNT_ENVIRONMENT_VARIABLE)):
        parser.error(
            f"${WORKER_COUNT_ENVIRONMENT_VARIABLE} names no process count; set it to a whole number of at least 1"
        )
    return arguments
