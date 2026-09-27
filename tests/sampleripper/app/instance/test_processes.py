from __future__ import annotations

import subprocess
import sys
from typing import Final

import psutil

from sampleripper.app.instance.processes import ProcessIdentity, current_process, end_process_tree, is_running

GRACE_SECONDS: Final[float] = 5.0
PARENT_PROGRAM: Final[str] = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "print(child.pid, flush=True)\n"
    "time.sleep(60)\n"
)


def test_this_process_is_running_and_a_later_one_with_its_id_is_not() -> None:
    identity = current_process()

    assert is_running(identity)
    assert not is_running(identity.model_copy(update={"started_at": identity.started_at - 3600.0}))


def test_an_ended_process_is_not_running() -> None:
    with subprocess.Popen([sys.executable, "-c", "pass"]) as ended:
        identity = ProcessIdentity(pid=ended.pid, started_at=psutil.Process(ended.pid).create_time())
        ended.wait()

    assert not is_running(identity)


def test_ending_a_process_ends_the_processes_it_started() -> None:
    with subprocess.Popen([sys.executable, "-c", PARENT_PROGRAM], stdout=subprocess.PIPE, text=True) as parent:
        assert parent.stdout is not None
        child_pid = int(parent.stdout.readline())
        child = psutil.Process(child_pid)
        identity = ProcessIdentity(pid=parent.pid, started_at=psutil.Process(parent.pid).create_time())

        end_process_tree(identity, grace_seconds=GRACE_SECONDS)

        assert parent.wait(timeout=GRACE_SECONDS) is not None
    psutil.wait_procs([child], timeout=GRACE_SECONDS)
    assert not child.is_running()


def test_a_process_started_later_under_the_same_id_is_left_alone() -> None:
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]) as bystander:
        started_at = psutil.Process(bystander.pid).create_time()

        end_process_tree(
            ProcessIdentity(pid=bystander.pid, started_at=started_at - 3600.0), grace_seconds=GRACE_SECONDS
        )

        assert bystander.poll() is None
        bystander.kill()
