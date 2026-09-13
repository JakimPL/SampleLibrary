from __future__ import annotations

from dataclasses import dataclass

import pytest

from sampleserver import cli

PROGRAM = "samplelibrary serve"
PUBLIC_HOST = "0.0.0.0"
OTHER_PORT = 8001
WORKER_COUNT = 4


@dataclass
class RecordedRun:
    application_path: str | None = None
    host: str | None = None
    port: int | None = None
    reload: bool | None = None
    workers: int | None = None


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> RecordedRun:
    """Captures what the serve command hands uvicorn, in place of binding a socket."""
    run = RecordedRun()

    def record(application_path: str, *, host: str, port: int, reload: bool, workers: int) -> None:
        run.application_path = application_path
        run.host = host
        run.port = port
        run.reload = reload
        run.workers = workers

    monkeypatch.setattr(cli.uvicorn, "run", record)
    return run


def test_the_api_serves_one_process_on_the_local_address_by_default(recorded: RecordedRun) -> None:
    cli.main([], prog=PROGRAM)

    assert recorded == RecordedRun(
        application_path=cli.APPLICATION_PATH,
        host=cli.DEFAULT_HOST,
        port=cli.DEFAULT_PORT,
        reload=False,
        workers=cli.DEFAULT_WORKERS,
    )


def test_flags_name_the_address_and_the_processes(recorded: RecordedRun) -> None:
    cli.main(["--host", PUBLIC_HOST, "--port", str(OTHER_PORT), "--workers", str(WORKER_COUNT)], prog=PROGRAM)

    assert (recorded.host, recorded.port, recorded.workers) == (PUBLIC_HOST, OTHER_PORT, WORKER_COUNT)


def test_reloading_serves_a_single_process(recorded: RecordedRun) -> None:
    cli.main(["--reload"], prog=PROGRAM)

    assert (recorded.reload, recorded.workers) == (True, cli.DEFAULT_WORKERS)


def test_reloading_and_several_workers_are_a_usage_error(
    recorded: RecordedRun, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["--reload", "--workers", str(WORKER_COUNT)], prog=PROGRAM)

    assert raised.value.code == 2
    assert "not allowed with" in capsys.readouterr().err
    assert recorded.application_path is None
