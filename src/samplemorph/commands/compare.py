from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Final

from pydantic import ValidationError
from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import ending_in_one_line
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplemorph.envelope.settings import (
    DEFAULT_EXCITATION,
    DEFAULT_TIMELINE,
    EnvelopeSettings,
    Excitation,
    Timeline,
)
from samplemorph.listening.comparing import (
    DEFAULT_LISTENING_WEIGHTS,
    DEFAULT_PATH_WEIGHTS,
    ComparedRoute,
    ComparisonWeights,
    blind_folders,
    compare_routes,
)
from samplemorph.listening.heard_pairs import (
    PairSampleMissing,
    SilentPairEnd,
    read_heard_pair,
)
from samplemorph.listening.pairs import PairSet, read_pair_set
from samplemorph.partials.presets import DEFAULT_PROFILE_NAME, PROFILE_PRESETS
from samplemorph.pipeline import load_route
from samplemorph.route_arguments import (
    add_model_argument,
    add_morpher_argument,
    add_vocoder_arguments,
    route_choice_from,
)
from samplemorph.routes.kinds import RouteKind
from samplemorph.routes.named import (
    NamedRoute,
    blend_route,
    envelope_route,
    latent_route,
    partials_route,
    transport_route,
)

COMMAND_NAME: Final[str] = "compare"
COMPARISON_DEVICE: Final[str] = "cpu"

_logger = logging.getLogger(__name__)


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = add_subcommand(
        commands,
        COMMAND_NAME,
        summary="Render drawn pairs through several morph routes side by side, and read every path.",
    )
    parser.add_argument("--pairs", type=str, required=True, help="The pairs file draw-pairs wrote.")
    parser.add_argument("--output", type=str, required=True, help="The directory to write the listening set into.")
    parser.add_argument(
        "--routes",
        type=RouteKind,
        nargs="+",
        choices=tuple(RouteKind),
        default=tuple(RouteKind),
        help="Which routes to render every pair through.",
    )
    parser.add_argument(
        "--weights", type=float, nargs="+", default=DEFAULT_PATH_WEIGHTS, help="The weights every path is read at."
    )
    parser.add_argument(
        "--listening-weights",
        type=float,
        nargs="+",
        default=DEFAULT_LISTENING_WEIGHTS,
        help="The path weights written as files of their own, beside both ends.",
    )
    parser.add_argument(
        "--profiles",
        type=str,
        nargs="+",
        choices=tuple(PROFILE_PRESETS),
        default=(DEFAULT_PROFILE_NAME,),
        help="Which middle every partials route takes, one route per profile.",
    )
    parser.add_argument(
        "--excitations",
        type=Excitation,
        nargs="+",
        choices=tuple(Excitation),
        default=(DEFAULT_EXCITATION,),
        help="Whose excitation every envelope route sounds under the moving envelope, one route per choice.",
    )
    parser.add_argument(
        "--timelines",
        type=Timeline,
        nargs="+",
        choices=tuple(Timeline),
        default=(DEFAULT_TIMELINE,),
        help="Whose course through time every envelope route is heard on, one route per choice.",
    )
    parser.add_argument(
        "--blind", action="store_true", help="Name every route's folder by a letter, the key kept in the manifest."
    )
    add_model_argument(parser)
    add_vocoder_arguments(parser, device_default=COMPARISON_DEVICE)
    add_morpher_argument(parser)


def run(connection: Connection, config: LibraryConfig, arguments: argparse.Namespace) -> None:
    """Render every pair of the file through every route named and write the listening set.

    The pairs, the weights and every sample are read before any model loads, so an unreadable file,
    a weight off the path or a sample gone from the catalog ends the process at once. The latent
    route loads the stored model the latent flags name; the transport, the blend and the partials
    read the samples' own analyses alone. The partials kind stands for one route per profile named
    and the envelope kind for one per excitation and course named, each under a folder of its own.

    Raises:
        SystemExit: the pairs file cannot be read, the weights do not describe a path, or a pair names
            a sample that cannot be read or is too quiet to hear.
    """
    with ending_in_one_line("Compared nothing", (ValueError,)):
        pair_set = _read_pairs(Path(arguments.pairs))
        weights = ComparisonWeights(path=tuple(arguments.weights), listening=tuple(arguments.listening_weights))
    audio = SampleAudio.from_catalog(connection, config.library_root)
    try:
        heard = tuple(read_heard_pair(connection, audio, pair, weights=weights.path) for pair in pair_set.pairs)
    except (PairSampleMissing, SilentPairEnd, SampleUnavailableError) as error:
        _logger.error("Compared nothing: %s.", error)
        sys.exit(ExitStatus.REFUSED)
    named = _named_routes(
        tuple(dict.fromkeys(arguments.routes)),
        profiles=tuple(dict.fromkeys(arguments.profiles)),
        excitations=tuple(dict.fromkeys(arguments.excitations)),
        timelines=tuple(dict.fromkeys(arguments.timelines)),
        config=config,
        arguments=arguments,
    )
    names = tuple(route.name for route in named)
    folders = blind_folders(names, random_seed=pair_set.seed) if arguments.blind else names
    routes = tuple(ComparedRoute(named=route, folder=folder) for route, folder in zip(named, folders, strict=True))
    summary = compare_routes(
        heard, pair_set=pair_set, routes=routes, weights=weights, output_directory=Path(arguments.output)
    )
    _logger.info(
        "Wrote %d pairs through %d routes into %s.", summary.pair_count, summary.route_count, summary.output_directory
    )


def _read_pairs(path: Path) -> PairSet:
    """The pair set a file holds.

    Raises:
        ValueError: the file cannot be read, or holds no valid pair set.
    """
    try:
        return read_pair_set(path)
    except (OSError, ValidationError) as error:
        raise ValueError(f"{path} holds no pair set to read ({error})") from error


def _named_routes(
    kinds: tuple[RouteKind, ...],
    *,
    profiles: tuple[str, ...],
    excitations: tuple[Excitation, ...],
    timelines: tuple[Timeline, ...],
    config: LibraryConfig,
    arguments: argparse.Namespace,
) -> tuple[NamedRoute, ...]:
    """Every route a run renders: one per kind, the partials kind per profile and the envelope kind per excitation and course."""
    routes: list[NamedRoute] = []
    for kind in kinds:
        match kind:
            case RouteKind.LATENT:
                routes.append(latent_route(load_route(config.library_root, route_choice_from(arguments))))
            case RouteKind.TRANSPORT:
                routes.append(transport_route())
            case RouteKind.BLEND:
                routes.append(blend_route())
            case RouteKind.PARTIALS:
                routes.extend(partials_route(name) for name in profiles)
            case RouteKind.ENVELOPE:
                routes.extend(
                    envelope_route(EnvelopeSettings(excitation=excitation, timeline=timeline))
                    for timeline in timelines
                    for excitation in excitations
                )
    return tuple(routes)
