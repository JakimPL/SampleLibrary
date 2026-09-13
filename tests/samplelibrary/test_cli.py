from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from samplecore.config import CONFIG_PATH_ENVIRONMENT_VARIABLE, DATABASE_URL_ENVIRONMENT_VARIABLE, load_config
from samplelibrary.cli import PROGRAM_NAME, dispatch
from samplelibrary.commands import COMMANDS, Command, CommandGroup, CommandRunner

PACKAGES_A_COMMAND_LOADS = (
    "sampleextract",
    "samplecloud",
    "samplemorph",
    "sampleserver",
    "sqlalchemy",
    "torch",
    "umap",
    "uvicorn",
)
GROUPS = tuple(entry for entry in COMMANDS if isinstance(entry, CommandGroup))
SANDBOX_DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/sandbox"
EXPORTED_DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/library"


@dataclass(frozen=True)
class RouteCase:
    command_line: list[str]
    target: str
    forwarded: list[str]
    program: str


@dataclass
class RecordedCall:
    argv: list[str] | None = None
    prog: str | None = None


ROUTE_CASES = (
    RouteCase(["setup", "database"], "samplelibrary.setup.main", ["database"], "samplelibrary setup"),
    RouteCase(["reset", "--confirm"], "samplelibrary.reset.main", ["--confirm"], "samplelibrary reset"),
    RouteCase(["extract", "--workers", "2"], "sampleextract.cli.main", ["--workers", "2"], "samplelibrary extract"),
    RouteCase(
        ["equivalence", "--limit", "5"],
        "sampleextract.equivalence.cli.main",
        ["--limit", "5"],
        "samplelibrary equivalence",
    ),
    RouteCase(["thumbnails", "--force"], "sampleextract.thumbnail_cli.main", ["--force"], "samplelibrary thumbnails"),
    RouteCase(["notes"], "sampleextract.notes.cli.main", [], "samplelibrary notes"),
    RouteCase(
        ["annotations", "export", "--path", "copy.jsonl"],
        "sampleextract.annotations.cli.main",
        ["export", "--path", "copy.jsonl"],
        "samplelibrary annotations",
    ),
    RouteCase(
        ["cloud", "embed", "--backend", "clap", "--label", "heard at the playback rate"],
        "samplecloud.cli.main",
        ["--backend", "clap", "--label", "heard at the playback rate"],
        "samplelibrary cloud embed",
    ),
    RouteCase(
        ["cloud", "placeholders"], "samplecloud.placeholder_modules.main", [], "samplelibrary cloud placeholders"
    ),
    RouteCase(
        ["cloud", "evaluate", "--experiment-id", "4", "--help"],
        "samplecloud.evaluation.cli.main",
        ["--experiment-id", "4", "--help"],
        "samplelibrary cloud evaluate",
    ),
    RouteCase(
        ["cloud", "suggest", "--experiment-id", "10"],
        "samplecloud.suggestions.cli.main",
        ["--experiment-id", "10"],
        "samplelibrary cloud suggest",
    ),
    RouteCase(
        ["morph", "cache-grids", "--cache", "codec", "--views", "0"],
        "samplemorph.cli.main",
        ["cache-grids", "--cache", "codec", "--views", "0"],
        "samplelibrary morph",
    ),
    RouteCase(["serve", "--reload"], "sampleserver.cli.main", ["--reload"], "samplelibrary serve"),
    RouteCase(["schema"], "sampleserver.openapi_export.main", [], "samplelibrary schema"),
    RouteCase(["tracking", "uri"], "samplelibrary.tracking.uri.main", [], "samplelibrary tracking uri"),
    RouteCase(
        ["tracking", "ui", "--port", "5001"],
        "samplelibrary.tracking.ui.main",
        ["--port", "5001"],
        "samplelibrary tracking ui",
    ),
)


@pytest.fixture
def recorded() -> RecordedCall:
    return RecordedCall()


def _recorder(recorded: RecordedCall) -> CommandRunner:
    def record(argv: list[str], *, prog: str) -> None:
        recorded.argv = argv
        recorded.prog = prog

    return record


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.program)
def test_a_command_line_reaches_the_command_it_names_with_the_rest_of_the_line(
    case: RouteCase, recorded: RecordedCall, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(case.target, _recorder(recorded))

    dispatch(case.command_line)

    assert (recorded.argv, recorded.prog) == (case.forwarded, case.program)


def _write_sandbox_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[library]\n"
        f'module_source_directory = "{(tmp_path / "modules").as_posix()}"\n'
        f'library_root = "{(tmp_path / "library").as_posix()}"\n'
        f'database_url = "{SANDBOX_DATABASE_URL}"\n',
        encoding="utf-8",
    )
    return config_path


def test_the_named_configuration_is_the_one_the_command_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENVIRONMENT_VARIABLE, str(tmp_path / "elsewhere.toml"))
    library_roots: list[Path] = []
    monkeypatch.setattr(
        "sampleextract.notes.cli.main", lambda argv, *, prog: library_roots.append(load_config().library_root)
    )

    dispatch(["--config", str(_write_sandbox_config(tmp_path)), "notes"])

    assert library_roots == [tmp_path / "library"]


def test_the_named_configuration_supplies_the_database_over_an_exported_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, EXPORTED_DATABASE_URL)
    database_urls: list[str] = []
    monkeypatch.setattr(
        "sampleextract.notes.cli.main", lambda argv, *, prog: database_urls.append(load_config().database_url)
    )

    dispatch(["--config", str(_write_sandbox_config(tmp_path)), "notes"])

    assert database_urls == [SANDBOX_DATABASE_URL]


@pytest.mark.parametrize(
    "command_line",
    [["--confirm", "reset"], ["--workers", "reset"], ["extract", "--config", "config.toml"], ["extract", "--config=x"]],
    ids=["an option before the command", "an unknown option before the command", "--config after", "--config= after"],
)
def test_an_argument_on_the_wrong_side_of_the_command_name_is_a_usage_error(
    command_line: list[str], recorded: RecordedCall, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("samplelibrary.reset.main", _recorder(recorded))
    monkeypatch.setattr("sampleextract.cli.main", _recorder(recorded))

    with pytest.raises(SystemExit) as raised:
        dispatch(command_line)

    assert raised.value.code == 2
    assert recorded.argv is None


@dataclass(frozen=True)
class LeafCommand:
    names: list[str]
    command: Command

    @property
    def program(self) -> str:
        return " ".join([PROGRAM_NAME, *self.names])


def _leaf_commands() -> list[LeafCommand]:
    leaves: list[LeafCommand] = []
    for entry in COMMANDS:
        match entry:
            case Command():
                leaves.append(LeafCommand([entry.name], entry))
            case CommandGroup():
                leaves.extend(LeafCommand([entry.name, command.name], command) for command in entry.commands)
    return leaves


def test_every_command_has_a_route_case() -> None:
    assert {leaf.program for leaf in _leaf_commands()} == {case.program for case in ROUTE_CASES}


@pytest.mark.parametrize("leaf", _leaf_commands(), ids=lambda leaf: leaf.program)
def test_a_command_describes_itself_as_the_command_list_does(
    leaf: LeafCommand, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        dispatch([*leaf.names, "--help"])

    help_text = " ".join(capsys.readouterr().out.split())
    assert raised.value.code == 0
    assert leaf.command.summary in help_text


@pytest.mark.parametrize("group", GROUPS, ids=lambda group: group.name)
def test_a_group_lists_every_command_it_holds(group: CommandGroup, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        dispatch([group.name, "--help"])

    listing = " ".join(capsys.readouterr().out.split())
    assert raised.value.code == 0
    assert all(command.name in listing and command.summary in listing for command in group.commands)


@pytest.mark.parametrize("command_line", [[], [GROUPS[0].name]], ids=["no command", "a group alone"])
def test_a_line_naming_no_command_is_a_usage_error(command_line: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        dispatch(command_line)

    assert raised.value.code == 2
    assert "required" in capsys.readouterr().err


@pytest.mark.parametrize("command_line", [["--help"], [GROUPS[0].name, "--help"]], ids=["commands", "a group"])
def test_listing_commands_loads_none_of_the_packages_they_run(command_line: list[str]) -> None:
    script = (
        "import sys\n"
        "from samplelibrary.cli import main\n"
        f"sys.argv = ['samplelibrary', *{command_line!r}]\n"
        "try:\n"
        "    main()\n"
        "except SystemExit:\n"
        "    pass\n"
        f"print(sorted(name for name in sys.modules if name.split('.')[0] in {PACKAGES_A_COMMAND_LOADS!r}))\n"
    )

    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)

    assert completed.stdout.splitlines()[-1] == "[]"
