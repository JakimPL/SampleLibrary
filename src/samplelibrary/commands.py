# pylint: disable=import-outside-toplevel
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol


class CommandRunner(Protocol):
    """Parses the rest of a command line and runs the command it belongs to.

    A runner imports its command's package as it runs, so listing the commands, or running a light
    one, loads only what that command uses and needs only the extras that command installs.
    """

    def __call__(self, argv: list[str], *, prog: str) -> None: ...


@dataclass(frozen=True, kw_only=True)
class Command:
    """A command a shell names, with the one line `samplelibrary --help` lists it by."""

    name: str
    summary: str
    run: CommandRunner


@dataclass(frozen=True, kw_only=True)
class CommandGroup:
    """Commands listed together under one name, each owned by a different module of one package."""

    name: str
    summary: str
    commands: tuple[Command, ...]


def _setup(argv: list[str], *, prog: str) -> None:
    from samplelibrary.setup import main

    main(argv, prog=prog)


def _reset(argv: list[str], *, prog: str) -> None:
    from samplelibrary.reset import main

    main(argv, prog=prog)


def _extract(argv: list[str], *, prog: str) -> None:
    from sampleextract.cli import main

    main(argv, prog=prog)


def _equivalence(argv: list[str], *, prog: str) -> None:
    from sampleextract.equivalence.cli import main

    main(argv, prog=prog)


def _thumbnails(argv: list[str], *, prog: str) -> None:
    from sampleextract.thumbnail_cli import main

    main(argv, prog=prog)


def _notes(argv: list[str], *, prog: str) -> None:
    from sampleextract.notes.cli import main

    main(argv, prog=prog)


def _annotations(argv: list[str], *, prog: str) -> None:
    from sampleextract.annotations.cli import main

    main(argv, prog=prog)


def _cloud_embed(argv: list[str], *, prog: str) -> None:
    from samplecloud.cli import main

    main(argv, prog=prog)


def _cloud_placeholders(argv: list[str], *, prog: str) -> None:
    from samplecloud.placeholder_modules import main

    main(argv, prog=prog)


def _cloud_evaluate(argv: list[str], *, prog: str) -> None:
    from samplecloud.evaluation.cli import main

    main(argv, prog=prog)


def _cloud_suggest(argv: list[str], *, prog: str) -> None:
    from samplecloud.suggestions.cli import main

    main(argv, prog=prog)


def _morph(argv: list[str], *, prog: str) -> None:
    from samplemorph.cli import main

    main(argv, prog=prog)


def _serve(argv: list[str], *, prog: str) -> None:
    from sampleserver.cli import main

    main(argv, prog=prog)


def _schema(argv: list[str], *, prog: str) -> None:
    from sampleserver.openapi_export import main

    main(argv, prog=prog)


def _tracking_uri(argv: list[str], *, prog: str) -> None:
    from samplelibrary.tracking.uri import main

    main(argv, prog=prog)


def _tracking_ui(argv: list[str], *, prog: str) -> None:
    from samplelibrary.tracking.ui import main

    main(argv, prog=prog)


COMMANDS: Final[tuple[Command | CommandGroup, ...]] = (
    Command(name="setup", summary="Put a config file in place, or prepare the databases it names.", run=_setup),
    Command(name="reset", summary="Empty the configured library's catalog and content store.", run=_reset),
    Command(name="extract", summary="Catalog every module under the configured source directory.", run=_extract),
    Command(
        name="equivalence",
        summary="Detect bit-depth, amplification and resampled variants among the cataloged samples.",
        run=_equivalence,
    ),
    Command(name="thumbnails", summary="Compute a waveform thumbnail for each cataloged sample.", run=_thumbnails),
    Command(
        name="notes", summary="Read the notes each module plays, and the rate each sample is heard at.", run=_notes
    ),
    Command(
        name="annotations", summary="Move hand-made sample annotations in and out of the catalog.", run=_annotations
    ),
    CommandGroup(
        name="cloud",
        summary="Describe samples as experiments, and place them on the cloud.",
        commands=(
            Command(
                name="embed", summary="Extract sample features and reduce them to cloud coordinates.", run=_cloud_embed
            ),
            Command(
                name="placeholders",
                summary="Place every cataloged module at a placeholder cloud coordinate.",
                run=_cloud_placeholders,
            ),
            Command(
                name="evaluate",
                summary="Score an experiment's descriptor against the catalog's own targets.",
                run=_cloud_evaluate,
            ),
            Command(
                name="suggest",
                summary="Suggest labels for every sample of a listening-model experiment.",
                run=_cloud_suggest,
            ),
        ),
    ),
    Command(
        name="morph",
        summary="Fit, train and render the decodable representation, and serve morphs over HTTP.",
        run=_morph,
    ),
    Command(name="serve", summary="Serve the library's API over HTTP.", run=_serve),
    Command(name="schema", summary="Print the API's OpenAPI schema as JSON, or write it to a file.", run=_schema),
    CommandGroup(
        name="tracking",
        summary="Find the run store every training and evaluation pass records to.",
        commands=(
            Command(
                name="uri", summary="Print the URI of the run store beside the configured library.", run=_tracking_uri
            ),
            Command(
                name="ui", summary="Browse the configured library's run store in MLflow's interface.", run=_tracking_ui
            ),
        ),
    ),
)
