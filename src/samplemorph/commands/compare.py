from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError
from sqlalchemy import Connection

from samplecore.cli_parsing import add_subcommand
from samplecore.cli_support import ending_in_one_line
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from samplecore.storage.sample_audio import SampleAudio, SampleUnavailableError
from samplemorph.geometry import log_frequency_geometry
from samplemorph.listening.comparing import (
    DEFAULT_LISTENING_WEIGHTS,
    DEFAULT_PATH_WEIGHTS,
    ComparedRoute,
    ComparisonWeights,
    blind_folders,
    compare_routes,
)
from samplemorph.listening.heard_pairs import PairSampleMissing, SilentPairEnd, read_heard_pair
from samplemorph.listening.pairs import PairSet, read_pair_set
from samplemorph.partials.morph import PartialMorph
from samplemorph.partials.presets import DEFAULT_PROFILE_NAME, PROFILE_PRESETS
from samplemorph.partials.profile import MorphProfile
from samplemorph.partials.settings import PartialSettings
from samplemorph.pipeline import latent_route_description, load_route
from samplemorph.route_arguments import (
    add_model_argument,
    add_morpher_argument,
    add_vocoder_arguments,
    route_choice_from,
)
from samplemorph.routes.analysis import AnalysisRoute, SpectralPath
from samplemorph.routes.kinds import RouteKind
from samplemorph.routes.latent import LatentRoute
from samplemorph.routes.partials import PartialRoute
from samplemorph.transport.blend import blend
from samplemorph.transport.morph import transport
from samplemorph.transport.settings import TransportSettings

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
    read the samples' own analyses alone. The partials kind stands for one route per profile named,
    each under a folder of its own.

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
    choices = _route_choices(tuple(dict.fromkeys(arguments.routes)), profiles=tuple(dict.fromkeys(arguments.profiles)))
    names = tuple(choice.name for choice in choices)
    folders = blind_folders(names, random_seed=pair_set.seed) if arguments.blind else names
    routes = tuple(
        _compared_route(choice, folder=folder, config=config, arguments=arguments)
        for choice, folder in zip(choices, folders, strict=True)
    )
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


@dataclass(frozen=True)
class _ProfiledRoute:
    """A partials route following one profile, which its name carries."""

    profile_name: str

    @property
    def kind(self) -> RouteKind:
        return RouteKind.PARTIALS

    @property
    def name(self) -> str:
        return f"{RouteKind.PARTIALS.value}-{self.profile_name}"


@dataclass(frozen=True)
class _PlainRoute:
    """A route its kind names on its own."""

    kind: RouteKind

    @property
    def name(self) -> str:
        return self.kind.value


_RouteChoice = _ProfiledRoute | _PlainRoute


def _route_choices(kinds: tuple[RouteKind, ...], *, profiles: tuple[str, ...]) -> tuple[_RouteChoice, ...]:
    """Every route a run renders, the partials kind standing for one route per profile named."""
    choices: list[_RouteChoice] = []
    for kind in kinds:
        if kind is RouteKind.PARTIALS:
            choices.extend(_ProfiledRoute(profile_name=name) for name in profiles)
        else:
            choices.append(_PlainRoute(kind=kind))
    return tuple(choices)


def _compared_route(
    choice: _RouteChoice, *, folder: str, config: LibraryConfig, arguments: argparse.Namespace
) -> ComparedRoute:
    match choice:
        case _ProfiledRoute():
            return _partials_route(choice, folder=folder, profile=PROFILE_PRESETS[choice.profile_name])
        case _PlainRoute(kind=RouteKind.LATENT):
            loaded = load_route(config.library_root, route_choice_from(arguments))
            return ComparedRoute(
                kind=choice.kind,
                name=choice.name,
                folder=folder,
                route=LatentRoute(loaded.route),
                description=latent_route_description(loaded),
            )
        case _PlainRoute(kind=RouteKind.BLEND):
            return _analysis_route(choice, folder=folder, path=blend)
        case _PlainRoute():
            return _analysis_route(choice, folder=folder, path=transport)


def _analysis_route(choice: _RouteChoice, *, folder: str, path: SpectralPath) -> ComparedRoute:
    geometry = log_frequency_geometry()
    settings = TransportSettings()
    return ComparedRoute(
        kind=choice.kind,
        name=choice.name,
        folder=folder,
        route=AnalysisRoute(path=path, geometry=geometry, settings=settings),
        description={"geometry": geometry.model_dump(mode="json"), "settings": settings.model_dump(mode="json")},
    )


def _partials_route(choice: _RouteChoice, *, folder: str, profile: MorphProfile) -> ComparedRoute:
    geometry = log_frequency_geometry()
    settings = TransportSettings()
    partial_settings = PartialSettings()
    return ComparedRoute(
        kind=choice.kind,
        name=choice.name,
        folder=folder,
        route=PartialRoute(
            morph=PartialMorph(profile=profile, geometry=geometry, settings=settings),
            partial_settings=partial_settings,
        ),
        description={
            "geometry": geometry.model_dump(mode="json"),
            "settings": settings.model_dump(mode="json"),
            "partial_settings": partial_settings.model_dump(mode="json"),
            "profile": profile.model_dump(mode="json"),
        },
    )
