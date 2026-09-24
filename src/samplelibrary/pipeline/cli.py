from __future__ import annotations

import argparse
import logging
import shutil
from collections.abc import Sequence
from typing import Final

from samplecore.cli_parsing import add_subcommand, command_parser
from samplecore.cli_support import bootstrap_cli, ending_in_one_line, open_catalog_connection
from samplecore.config import ConfigurationError, resolve_config_path
from samplecore.exit_status import ExitStatus
from samplelibrary.limits.ceiling import MalformedCeiling
from samplelibrary.limits.probe import memory_scope
from samplelibrary.pipeline.context import PipelineContext, RunSession
from samplelibrary.pipeline.events import ConsoleLog, EventFile, EventSink, Sinks
from samplelibrary.pipeline.graph import StepGraph, UnknownTarget
from samplelibrary.pipeline.layout import PipelineLayout, RunPaths
from samplelibrary.pipeline.locks import claim_pipeline_lock
from samplelibrary.pipeline.programs import ProgramResolver, SampleLibraryPrograms
from samplelibrary.pipeline.scheduler import RunRequest, run_pipeline
from samplelibrary.pipeline.settings import PipelineSettings, read_pipeline_settings
from samplelibrary.pipeline.status import read_status, report_last_attempts, report_status
from samplelibrary.pipeline.steps.library import library_graph, settings_model

RUN_COMMAND: Final[str] = "run"
STATUS_COMMAND: Final[str] = "status"
REFUSALS: Final[tuple[type[ValueError], ...]] = (UnknownTarget, MalformedCeiling)

_logger = logging.getLogger(__name__)


def main(argv: list[str], *, prog: str) -> None:
    """Build the library through its steps, or say what each of them would do now."""
    run_pipeline_command(argv, prog=prog, resolver=SampleLibraryPrograms(), extra_sinks=())


def run_pipeline_command(
    argv: list[str], *, prog: str, resolver: ProgramResolver, extra_sinks: Sequence[EventSink]
) -> None:
    """The pipeline's composition root, which the command line and anything standing in for its programs start from.

    `resolver` names the program each step runs, and `extra_sinks` take every event beside the
    console and the run's own event file.

    Raises:
        SystemExit: the configuration was refused, or the run ended some other way than completed.
    """
    arguments = parse_arguments(argv, prog=prog)
    config = bootstrap_cli()
    try:
        settings = read_pipeline_settings()
    except ConfigurationError as error:
        _logger.error("Configuration error: %s", error)
        raise SystemExit(ExitStatus.REFUSED) from error
    graph = library_graph()
    _require_readable_step_tables(settings, graph)
    targets = tuple(arguments.targets)
    with ending_in_one_line("Ran nothing", REFUSALS):
        graph.order(targets)

    with open_catalog_connection(config.catalog_url()) as connection:
        context = PipelineContext(
            config=config,
            settings=settings,
            connection=connection,
            layout=PipelineLayout(library_root=config.library_root),
        )
        if arguments.command == STATUS_COMMAND:
            _report(context, graph, targets)
            return
        session = RunSession(
            context=context,
            run=RunPaths.opened_under(context.layout),
            resolver=resolver,
            scope=memory_scope(),
        )
        _run(session, graph, arguments, extra_sinks)


def _require_readable_step_tables(settings: PipelineSettings, graph: StepGraph) -> None:
    """Refuse a step table naming a step this pipeline does not hold, or holding a setting its step does not read.

    Raises:
        SystemExit: a table names no step of this pipeline, or a setting or value its step does not read.
    """
    known = {step.name for step in graph.steps}
    unknown = sorted(set(settings.steps) - known)
    if unknown:
        _logger.error(
            "Configuration error: [pipeline.%s] names no step of this pipeline, which holds %s.",
            unknown[0],
            ", ".join(sorted(known)),
        )
        raise SystemExit(ExitStatus.REFUSED)
    for step in sorted(settings.steps):
        try:
            settings.settings_for(step, settings_model(step))
        except ConfigurationError as error:
            _logger.error("Configuration error: %s", error)
            raise SystemExit(ExitStatus.REFUSED) from error


def _report(context: PipelineContext, graph: StepGraph, targets: tuple[str, ...]) -> None:
    """Say what each step would do now, and how each ended the last time a run tried it."""
    with ending_in_one_line("Read nothing", REFUSALS):
        report_status(read_status(context, graph, targets))
    report_last_attempts(context.layout)


def _run(
    session: RunSession, graph: StepGraph, arguments: argparse.Namespace, extra_sinks: Sequence[EventSink]
) -> None:
    """Take the run this command line asks for, ending with the status its outcome deserves.

    Raises:
        SystemExit: the run ended some other way than completed.
    """
    sinks = Sinks([ConsoleLog(), EventFile(session.run.events), *extra_sinks])
    _snapshot_the_configuration(session)
    request = RunRequest(
        targets=tuple(arguments.targets),
        from_scratch=arguments.from_scratch,
        redo=tuple(arguments.redo),
        follow=arguments.follow,
    )
    with open_catalog_connection(session.context.config.catalog_url()) as lock_connection:
        lock = claim_pipeline_lock(lock_connection, session.context.library_identity)
        with ending_in_one_line("Ran nothing", REFUSALS):
            report = run_pipeline(session, graph, request, sinks, lock)

    _logger.info("The run's events and logs are under %s.", session.run.directory)
    if report.exit_status is not ExitStatus.COMPLETED:
        raise SystemExit(report.exit_status)


def _snapshot_the_configuration(session: RunSession) -> None:
    """Copy the configuration this run reads into the run's own directory, which every step then reads.

    A configuration edited while a long run goes on leaves that run reading the library it started on.
    """
    shutil.copyfile(resolve_config_path(), session.run.config_snapshot)


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
