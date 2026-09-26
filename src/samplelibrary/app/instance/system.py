from __future__ import annotations

import time

import httpx

from samplelibrary.app.installation import Reply, ask_to_quit, reply_at
from samplelibrary.app.instance.processes import ProcessIdentity, end_process_tree, is_running


class SystemProcesses:
    """The processes of this machine, as a takeover reads and ends them."""

    def is_running(self, identity: ProcessIdentity) -> bool:
        return is_running(identity)

    def end_tree(self, identity: ProcessIdentity, *, grace_seconds: float) -> None:
        end_process_tree(identity, grace_seconds=grace_seconds)


class HttpContact:
    """The running application's setup routes, reached over HTTP at the address its record names."""

    def __init__(self, *, setup_prefix: str, timeout: httpx.Timeout) -> None:
        self._setup_prefix = setup_prefix
        self._timeout = timeout

    def reply(self, address: str) -> Reply:
        with self._client(address) as setup:
            return reply_at(setup)

    def ask_to_quit(self, address: str, *, seconds: float) -> None:
        with self._client(address) as setup:
            ask_to_quit(setup, seconds=seconds)

    def _client(self, address: str) -> httpx.Client:
        return httpx.Client(base_url=f"{address.rstrip('/')}{self._setup_prefix}", timeout=self._timeout)


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
