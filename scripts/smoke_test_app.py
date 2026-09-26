from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

LOOPBACK: Final[str] = "127.0.0.1"
POLL_SECONDS: Final[float] = 2.0
REQUEST_SECONDS: Final[float] = 10.0
INSTALL_SECONDS: Final[float] = 3600.0
OPEN_SECONDS: Final[float] = 300.0
BUILD_SECONDS: Final[float] = 900.0
QUIT_SECONDS: Final[float] = 120.0
MODULES_DIRECTORY_NAME: Final[str] = "modules"
LIBRARY_DIRECTORY_NAME: Final[str] = "library"
CONFIG_FILE_NAME: Final[str] = "config.toml"
CONFIG_PATH_ENVIRONMENT_VARIABLE: Final[str] = "SAMPLELIBRARY_CONFIG"
SERVER_PID_FILE: Final[Path] = Path("postgres") / "data" / "postmaster.pid"
BUILD_TARGET: Final[str] = "catalog"
WRITE_MODULES: Final[str] = """
import sys
from pathlib import Path
from samplelibrary.sandbox.modules import sandbox_modules
target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
for name, content in sandbox_modules().items():
    (target / name).write_bytes(content)
"""

State = dict[str, object]


class SmokeTestError(Exception):
    """Raised when the application misses one step of the smoke test."""


@dataclass(frozen=True)
class Application:
    """Where the application under test answers.

    The port is one no program held as the test began, so an application already running on this
    machine keeps its own port and stays out of the test.
    """

    port: int

    @property
    def setup_route(self) -> str:
        return f"http://{LOOPBACK}:{self.port}/api/setup"

    @property
    def stats_route(self) -> str:
        return f"http://{LOOPBACK}:{self.port}/api/stats"


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a built executable, build a small library in it through the setup pages' API, and quit it."
    )
    parser.add_argument("--executable", type=Path, required=True, help="The executable `just executable` built.")
    parser.add_argument("--work", type=Path, required=True, help="An empty folder for the modules and the library.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Walk a fresh installation through a person's first session: install, choose folders, build, quit.

    The executable installs itself on its first start, so the first wait covers the download of
    Python and every package. The library is built from the sandbox's generated modules, written by
    the Python the executable installed, and its catalog must list them before the application quits
    and stops its database.

    Raises:
        SystemExit: the application missed a step, with what it reported.
    """
    arguments = _parse_arguments(argv)
    executable = arguments.executable.resolve()
    work = arguments.work.resolve()
    # A config file of its own in the work folder, so each run starts a fresh library of its own.
    environment = {**os.environ, CONFIG_PATH_ENVIRONMENT_VARIABLE: str(work / CONFIG_FILE_NAME)}
    application = Application(port=_free_port())
    launch = subprocess.Popen(  # pylint: disable=consider-using-with
        [executable, "--no-browser", "--port", str(application.port)], env=environment
    )
    try:
        _first_session(executable, work, launch, application)
    except SmokeTestError as error:
        sys.exit(f"Smoke test failed: {error}")
    finally:
        _stop(application, launch)
    print("Smoke test passed.")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((LOOPBACK, 0))
        port: int = probe.getsockname()[1]
    return port


def _first_session(executable: Path, work: Path, launch: subprocess.Popen[bytes], application: Application) -> None:
    modules = work / MODULES_DIRECTORY_NAME
    library_root = work / LIBRARY_DIRECTORY_NAME
    state = _wait_for_state(application, lambda state: "status" in state, seconds=INSTALL_SECONDS, launch=launch)
    _step(f"The application answers with status {state['status']}.")
    _write_modules(executable, modules)
    _step(f"Wrote the sandbox modules into {modules}.")
    _request("PUT", f"{application.setup_route}/sources", _sources(library_root, modules))
    state = _wait_for_state(application, lambda state: state["status"] in ("ready", "failed"), seconds=OPEN_SECONDS)
    if state["status"] != "ready":
        raise SmokeTestError(f"the library did not open: {state['problem']}")
    _step("The library is open.")
    _request("POST", f"{application.setup_route}/builds", {"target": BUILD_TARGET})
    _check_build(_wait_for_state(application, _build_ended, seconds=BUILD_SECONDS))
    _check_catalog(application)
    _quit(application)
    _wait_until_closed(application)
    launch.wait(timeout=QUIT_SECONDS)
    _step("The application quit.")
    if (library_root / SERVER_PID_FILE).exists():
        raise SmokeTestError("the library's database is still running after the application quit")
    _step("The library's database stopped.")


def _write_modules(executable: Path, directory: Path) -> None:
    """Write the sandbox's modules with the installed interpreter, which PyApp's `self python-path` names."""
    python = subprocess.run(
        [executable, "self", "python-path"], check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run([python, "-c", WRITE_MODULES, str(directory)], check=True)


def _sources(library_root: Path, modules: Path) -> dict[str, object]:
    return {
        "library_root": str(library_root),
        "module_source_directory": str(modules),
        "sample_directories": [],
        "sample_exclusions": [],
    }


def _build_ended(state: State) -> bool:
    build = state["build"]
    return isinstance(build, dict) and build["status"] != "running"


def _check_build(state: State) -> None:
    build = state["build"]
    assert isinstance(build, dict)
    if build["status"] != "completed":
        log_tail = "\n".join(build["log_tail"])
        raise SmokeTestError(f"the build ended {build['status']}: {build['problem']}\n{log_tail}")
    _step(f"The {BUILD_TARGET} build completed.")


def _check_catalog(application: Application) -> None:
    stats = _request("GET", application.stats_route, None)
    if not isinstance(stats, dict) or not stats["module_count"]:
        raise SmokeTestError(f"the catalog lists no modules: {stats}")
    _step(f"The catalog lists {stats['module_count']} modules and {stats['sample_count']} samples.")


def _wait_for_state(
    application: Application,
    accept: Callable[[State], bool],
    *,
    seconds: float,
    launch: subprocess.Popen[bytes] | None = None,
) -> State:
    """Poll the setup state until it passes ``accept``.

    The executable may hand the application over to a process of its own and end, so only a failed
    ending of ``launch`` stops the wait early.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if launch is not None and launch.poll() not in (None, 0):
            raise SmokeTestError(f"the executable ended with exit code {launch.returncode}")
        state = _answered_state(application)
        if state is not None and accept(state):
            return state
        time.sleep(POLL_SECONDS)
    raise SmokeTestError(f"no expected answer within {seconds:.0f} seconds")


def _wait_until_closed(application: Application) -> None:
    deadline = time.monotonic() + QUIT_SECONDS
    while time.monotonic() < deadline:
        if _answered_state(application) is None:
            return
        time.sleep(POLL_SECONDS)
    raise SmokeTestError(f"the application still answers {QUIT_SECONDS:.0f} seconds after Quit")


def _answered_state(application: Application) -> State | None:
    """The setup state, or None while nothing answers at the application's address."""
    try:
        state = _request("GET", f"{application.setup_route}/state", None)
    except OSError:
        return None
    assert isinstance(state, dict)
    return state


def _stop(application: Application, launch: subprocess.Popen[bytes]) -> None:
    """Ask the application to quit where it still answers, and end the executable if it still runs."""
    if _answered_state(application) is not None:
        _quit(application)
    try:
        launch.wait(timeout=QUIT_SECONDS)
    except subprocess.TimeoutExpired:
        launch.kill()


def _quit(application: Application) -> None:
    """Ask the application to quit, which it answers once its library is closed."""
    _request("POST", f"{application.setup_route}/quit", None, seconds=QUIT_SECONDS)


def _request(method: str, url: str, body: dict[str, object] | None, *, seconds: float = REQUEST_SECONDS) -> object:
    """Send one request, and return its decoded JSON answer.

    Raises:
        SmokeTestError: the application answers with an error.
        OSError: nothing answers at the address.
    """
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=seconds) as response:
            content = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SmokeTestError(f"{method} {url} answered {error.code}: {detail}") from error
    return json.loads(content) if content else None


def _step(message: str) -> None:
    print(f"==> {message}", flush=True)


if __name__ == "__main__":
    main()
