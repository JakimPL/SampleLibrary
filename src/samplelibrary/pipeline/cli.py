from __future__ import annotations

import argparse
import logging
import shutil
from typing import Final

from samplecore.cli_parsing import add_subcommand, command_parser
from samplecore.cli_support import bootstrap_cli, ending_in_one_line, open_catalog_connection
from samplecore.config import ConfigurationError, resolve_config_path
from samplecore.exit_status import ExitStatus
from samplelibrary.limits.ceiling import MalformedCeiling
from samplelibrary.limits.probe import memory_scope
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.events import ConsoleLog, EventFile, Sinks
from samplelibrary.pipeline.graph import StepGraph, UnknownTarget
from samplelibrary.pipeline.layout import PipelineLayout, RunPaths
from samplelibrary.pipeline.locks import claim_pipeline_lock
from samplelibrary.pipeline.programs import SampleLibraryPrograms
from samplelibrary.pipeline.results import RunOutcome
from samplelibrary.pipeline.scheduler import RedoRefused, RunRequest, run_pipeline
from samplelibrary.pipeline.scratch import scratch_is_unfinished, start_from_scratch
from samplelibrary.pipeline.settings import read_pipeline_settings
from samplelibrary.pipeline.status import read_status, report_last_attempts, report_status
from samplelibrary.pipeline.steps.library import library_graph

RUN_COMMAND: Final[str] = "run"
STATUS_COMMAND: Final[str] = "status"
REFUSALS: Final[tuple[type[ValueError], ...]] = (UnknownTarget, RedoRefused, MalformedCeiling)

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Build the library through its steps, or say what each of them would do now."""
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    try:
        settings = read_pipeline_settings()
    except ConfigurationError as error:
        _logger.error("Configuration error: %s", error)
        raise SystemExit(ExitStatus.REFUSED) from error
    graph = library_graph()
    targets = tuple(arguments.targets)
    with ending_in_one_line("Ran nothing", REFUSALS):
        graph.order(targets)

    with open_catalog_connection(config.database_url) as connection:
        layout = PipelineLayout(library_root=config.library_root)
        run = RunPaths.opened_under(layout)
        context = PipelineContext(
            config=config,
            settings=settings,
            connection=connection,
            layout=layout,
            run=run,
            resolver=SampleLibraryPrograms(),
            scope=memory_scope(),
        )
        if arguments.command == STATUS_COMMAND:
            _report(context, graph, targets)
            return
        _run(context, graph, arguments, targets)


def _report(context: PipelineContext, graph: StepGraph, targets: tuple[str, ...]) -> None:
    """Say what each step would do now, and how each ended the last time a run tried it."""
    with ending_in_one_line("Read nothing", REFUSALS):
        report_status(read_status(context, graph, targets))
    report_last_attempts(context)


def _run(context: PipelineContext, graph: StepGraph, arguments: argparse.Namespace, targets: tuple[str, ...]) -> None:
    """Take the run this command line asks for, ending with the status its outcome deserves.

    Raises:
        SystemExit: another run holds this library, a step of it is still running, or a step failed.
    """
    sinks = Sinks([ConsoleLog(), EventFile(context.run.events)])
    _snapshot_the_configuration(context)
    with open_catalog_connection(context.config.database_url) as lock_connection:
        lock = claim_pipeline_lock(lock_connection, context.library_identity)
        if lock is None:
            _logger.error("Ran nothing: another run holds this library.")
            raise SystemExit(ExitStatus.REFUSED)
        if arguments.from_scratch or scratch_is_unfinished(context.layout):
            stopped = start_from_scratch(context, sinks)
            if stopped is not None:
                _logger.error("Emptied nothing: the reset ended %s; see %s.", stopped.outcome.value, stopped.log)
                raise SystemExit(ExitStatus.FAILED)
        with ending_in_one_line("Ran nothing", REFUSALS):
            report = run_pipeline(
                context,
                graph,
                RunRequest(targets=targets, redo=tuple(arguments.redo), follow=arguments.follow),
                sinks,
                lock,
            )

    _logger.info("The run's events and logs are under %s.", context.run.directory)
    if report.outcome is not RunOutcome.COMPLETED:
        raise SystemExit(ExitStatus.REFUSED if report.outcome is RunOutcome.REFUSED else ExitStatus.FAILED)


def _snapshot_the_configuration(context: PipelineContext) -> None:
    """Copy the configuration this run reads into the run's own directory, which every step then reads.

    A configuration edited while a long run goes on leaves that run reading the library it started on.
    """
    shutil.copyfile(resolve_config_path(), context.run.config_snapshot)


def parse_arguments(argv: list[str], *, prog: str) -> argparse.Namespace:
    parser = command_parser(prog=prog, description="Build the library through its steps, or say what each would do.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = add_subcommand(commands, RUN_COMMAND, summary="Take every step of the named targets that has work left.")
    run.add_argument("targets", nargs="*", help="Which targets to build; every one when left out.")
    run.add_argument(
        "--from-scratch",
        action="store_true",
        help="Empty the catalog and everything the pipeline built first, so every step runs again.",
    )
    run.add_argument(
        "--redo",
        action="append",
        default=[],
        metavar="STEP",
        help="Build this step's own output again, whatever the outputs say; may be given more than once.",
    )
    run.add_argument("--follow", action="store_true", help="Name each step's log as it starts.")
    status = add_subcommand(commands, STATUS_COMMAND, summary="Say what each step of the named targets would do now.")
    status.add_argument("targets", nargs="*", help="Which targets to read; every one when left out.")
    return parser.parse_args(argv)
