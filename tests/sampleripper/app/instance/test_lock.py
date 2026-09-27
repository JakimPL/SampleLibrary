from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Final

from sampleripper.app.instance.lock import try_lock

HOLDING_PROGRAM: Final[str] = (
    "import pathlib, sys, time\n"
    "from sampleripper.app.instance.lock import try_lock\n"
    "lock = try_lock(pathlib.Path(sys.argv[1]))\n"
    "print('held' if lock is not None else 'refused', flush=True)\n"
    "time.sleep(60)\n"
)


def test_a_held_lock_refuses_a_second_holder_until_it_is_released(tmp_path: Path) -> None:
    path = tmp_path / "instance.lock"

    first = try_lock(path)
    assert first is not None
    assert try_lock(path) is None
    first.release()

    second = try_lock(path)
    assert second is not None
    second.release()


def test_a_lock_comes_free_when_the_process_holding_it_is_killed(tmp_path: Path) -> None:
    path = tmp_path / "instance.lock"
    with subprocess.Popen(
        [sys.executable, "-c", HOLDING_PROGRAM, str(path)], stdout=subprocess.PIPE, text=True
    ) as holder:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held"
        assert try_lock(path) is None
        holder.kill()
        holder.wait()

    lock = try_lock(path)
    assert lock is not None
    lock.release()
