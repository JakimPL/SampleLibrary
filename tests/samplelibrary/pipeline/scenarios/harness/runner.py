from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from samplecore.config import ConfigurationError
from samplelibrary.pipeline.graph import StepGraph
from samplelibrary.pipeline.results import RunOutcome
from samplelibrary.pipeline.status import StepStatus, read_status
from samplelibrary.pipeline.steps.library import library_graph
from tests.samplelibrary.pipeline.scenarios.harness.expect import Expect
from tests.samplelibrary.pipeline.scenarios.harness.observe import RunObservation, observe_run, read_evidence
from tests.samplelibrary.pipeline.scenarios.harness.oracles import (
    check_delta,
    check_evidence,
    check_expectation,
    check_hygiene,
    check_settled,
    check_status_agreement,
)
from tests.samplelibrary.pipeline.scenarios.harness.plans import (
    REACHED_SUFFIX,
    RELEASE_SUFFIX,
    FaultPlan,
    GateMoment,
    HostPlan,
    KillPoint,
    gate_path,
)
from tests.samplelibrary.pipeline.scenarios.harness.world import CATALOG_PARTS, World

HOST_MODULE: Final[str] = "tests.samplelibrary.pipeline.scenarios.harness.host"
REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[5]
RUN_DEADLINE_SECONDS: Final[float] = 7200.0
GATE_DEADLINE_SECONDS: Final[float] = 300.0
POLL_SECONDS: Final[float] = 0.02
KILLED_STATUS: Final[int] = -signal.SIGKILL
CLOSING_DEADLINE_SECONDS: Final[float] = 60.0


@dataclass(frozen=True)
class Run:
    """One pipeline command in a scenario: what it asks for, the steps it scripts, and where it dies."""

    targets: tuple[str, ...] = ()
    from_scratch: bool = False
    redo: tuple[str, ...] = ()
    faults: FaultPlan = field(default_factory=FaultPlan)
    kill_at: KillPoint | None = None

    @property
    def argv(self) -> tuple[str, ...]:
        """The words after `samplelibrary pipeline` a person would type for this run."""
        words = ["run", *self.targets]
        if self.from_scratch:
            words.append("--from-scratch")
        for step in self.redo:
            words.extend(["--redo", step])
        return tuple(words)

    @property
    def reads_status_first(self) -> bool:
        """Whether `status` read right before this run describes what the run then decides."""
        return not self.from_scratch and not self.redo


@dataclass
class Host:
    """One pipeline command running in a process of its own, which a scenario acts on while it runs."""

    process: subprocess.Popen[bytes]
    request: Run
    act: Path
    before: dict[str, str]
    statuses: tuple[StepStatus, ...] | None

    @property
    def ledger(self) -> Path:
        return self.act / "ledger.jsonl"

    @property
    def events(self) -> Path:
        return self.act / "events.jsonl"

    @property
    def gates(self) -> Path:
        return self.act / "gates"

    def wait_at(self, step: str, moment: GateMoment) -> int:
        """Wait until a scripted step stands at its gate, answering that step's process id."""
        reached = _gate(self.gates, step, moment, REACHED_SUFFIX)
        deadline = time.monotonic() + GATE_DEADLINE_SECONDS
        while not reached.is_file() or not reached.read_text(encoding="utf-8"):
            if self.process.poll() is not None and not reached.is_file():
                raise AssertionError(f"the run ended with {self.process.returncode} before {step} reached {moment}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"{step} reached no {moment} gate in {GATE_DEADLINE_SECONDS} seconds")
            time.sleep(POLL_SECONDS)
        return int(reached.read_text(encoding="utf-8"))

    def reaches(self, step: str, moment: GateMoment) -> bool:
        """Wait until a scripted step stands at its gate or the run ends, answering whether the step got there."""
        reached = _gate(self.gates, step, moment, REACHED_SUFFIX)
        deadline = time.monotonic() + GATE_DEADLINE_SECONDS
        while not reached.is_file():
            if self.process.poll() is not None:
                return reached.is_file()
            if time.monotonic() > deadline:
                raise TimeoutError(f"{step} reached no {moment} gate in {GATE_DEADLINE_SECONDS} seconds")
            time.sleep(POLL_SECONDS)
        return True

    def wait_for_output(self, text: str) -> None:
        """Wait until the run's own output says something, which is how a scenario meets it between signals."""
        output = self.act / "host.log"
        deadline = time.monotonic() + GATE_DEADLINE_SECONDS
        while text not in output.read_text(encoding="utf-8", errors="replace"):
            if self.process.poll() is not None:
                raise AssertionError(f"the run ended with {self.process.returncode} before it said {text!r}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"the run never said {text!r} in {GATE_DEADLINE_SECONDS} seconds")
            time.sleep(POLL_SECONDS)

    def release(self, step: str, moment: GateMoment) -> None:
        """Let a step standing at its gate go on."""
        _gate(self.gates, step, moment, RELEASE_SUFFIX).write_text("go", encoding="utf-8")

    def interrupt(self) -> None:
        """Interrupt the run the way Ctrl+C in its terminal does: SIGINT to its foreground process group."""
        os.killpg(self.process.pid, signal.SIGINT)

    def terminate(self) -> None:
        os.kill(self.process.pid, signal.SIGTERM)

    def kill(self) -> None:
        """Kill the run's own process outright, leaving whatever step it started running on."""
        os.kill(self.process.pid, signal.SIGKILL)

    def wait(self) -> int:
        try:
            return self.process.wait(timeout=RUN_DEADLINE_SECONDS)
        except subprocess.TimeoutExpired:
            self.process.kill()
            raise


@dataclass
class ScenarioRunner:
    """Acts on one world and holds every run it makes to what the scenario says about it.

    Every run is checked against its expectation, the evidence it left behind, the catalog delta the
    scenario declared, what `status` said right before it, and, once it completes, a status that
    reads the library settled.
    """

    world: World
    stands_in: bool = True
    graph: StepGraph = field(default_factory=library_graph)
    acts: int = field(default=0, init=False)
    hosts: list[Host] = field(default_factory=list, init=False)

    def run(self, request: Run, expect: Expect, *, story: str, still_running: tuple[str, ...] = ()) -> RunObservation:
        """Run the pipeline once to its end, holding it to every oracle.

        `still_running` names the locks another run of the scenario still holds when this one ends.
        """
        return self.finish(self.start(request), expect, story=story, still_running=still_running)

    def start(self, request: Run) -> Host:
        """Start a run and answer it while it goes on, for a scenario acting on the library meanwhile."""
        self.acts += 1
        act = self.world.root / "acts" / f"{self.acts:02d}"
        act.mkdir(parents=True)
        statuses = self._status_before(request)
        before = self.world.catalog_digests()
        plan = HostPlan(
            config=self.world.config,
            argv=request.argv,
            faults=request.faults,
            ledger=act / "ledger.jsonl",
            gates=act / "gates",
            events=act / "events.jsonl",
            stands_in=self.stands_in,
            kill_at=request.kill_at,
        )
        plan_path = act / "plan.json"
        plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
        with (act / "host.log").open("wb") as output:
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                [sys.executable, "-m", HOST_MODULE, str(plan_path)],
                stdout=output,
                stderr=subprocess.STDOUT,
                cwd=REPOSITORY_ROOT,
                env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT)},
                start_new_session=True,
            )
        host = Host(process=process, request=request, act=act, before=before, statuses=statuses)
        self.hosts.append(host)
        return host

    def finish(
        self, host: Host, expect: Expect, *, story: str, settles: bool = True, still_running: tuple[str, ...] = ()
    ) -> RunObservation:
        """Wait for a started run to end, then hold it to its expectation and every oracle.

        `settles` is false for a run whose library a scenario changed while it ran, which leaves a
        later run work to do, and `still_running` names the locks another run still holds.
        """
        observation = observe_run(self.world.layout, host.events, host.wait())
        check_expectation(observation, expect, story)
        after = self._hold_to_oracles(
            host, observation, expect, story=story, settles=settles, still_running=still_running
        )
        check_delta(host.before, after, expect, story)
        return observation

    def explore(self, host: Host, *, story: str) -> RunObservation:
        """Wait for a started run to end, then hold it to every oracle, stating nothing about what it should have done."""
        observation = observe_run(self.world.layout, host.events, host.wait())
        self._hold_to_oracles(
            host, observation, Expect.observed(observation), story=story, settles=True, still_running=()
        )
        return observation

    def _hold_to_oracles(  # pylint: disable=too-many-arguments
        self,
        host: Host,
        observation: RunObservation,
        shown: Expect,
        *,
        story: str,
        settles: bool,
        still_running: tuple[str, ...],
    ) -> dict[str, str]:
        """Hold a run to what it left behind, what status said before and after it, and the locks it let go; answer the world after it."""
        check_evidence(observation, read_evidence(observation, host.ledger), story, shown)
        after = self.world.catalog_digests()
        if host.statuses is not None and settles:
            catalog_moved = any(host.before[part] != after[part] for part in CATALOG_PARTS)
            check_status_agreement(host.statuses, observation, self.graph, story, shown, catalog_moved=catalog_moved)
        if observation.outcome is RunOutcome.COMPLETED and settles:
            check_settled(self.status(host.request.targets), self.graph, story)
        if observation.exit_status != KILLED_STATUS:
            check_hygiene(tuple(lock for lock in self.world.stray_locks() if lock not in still_running), story)
        return after

    def _status_before(self, request: Run) -> tuple[StepStatus, ...] | None:
        """What `status` says right before a run, where it describes what the run decides and can be read at all."""
        if not request.reads_status_first:
            return None
        try:
            return self.status(request.targets)
        except ConfigurationError:
            return None

    def status(self, targets: tuple[str, ...]) -> tuple[StepStatus, ...]:
        """What `status` says about every step of these targets now."""
        statuses = read_status(self.world.context(), self.graph, targets)
        self.world.connection.rollback()
        return statuses

    def close(self) -> None:
        """Stop whatever a scenario left running: every run still going, and every step waiting at a gate."""
        for host in self.hosts:
            if host.process.poll() is None:
                host.kill()
                host.process.wait()
            for reached in host.gates.glob(f"*{REACHED_SUFFIX}"):
                reached.with_name(reached.name.removesuffix(REACHED_SUFFIX) + RELEASE_SUFFIX).write_text(
                    "go", encoding="utf-8"
                )
        wait_until_released(self.world, CLOSING_DEADLINE_SECONDS)


def wait_until_released(world: World, deadline_seconds: float) -> None:
    """Wait until no process holds a lock of this world beyond the ones the scenario holds itself."""
    deadline = time.monotonic() + deadline_seconds
    while world.stray_locks():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{', '.join(world.stray_locks())} still held after {deadline_seconds} seconds")
        time.sleep(POLL_SECONDS * 5)


def _gate(gates: Path, step: str, moment: GateMoment, suffix: str) -> Path:
    path = gate_path(gates, step, moment)
    return path.with_name(path.name + suffix)
