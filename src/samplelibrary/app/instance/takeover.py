from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum, unique
from typing import Protocol

from samplelibrary.app.installation import Reply
from samplelibrary.app.instance.lock import HeldLock, try_lock
from samplelibrary.app.instance.place import InstancePlace
from samplelibrary.app.instance.processes import ProcessIdentity
from samplelibrary.app.instance.record import InstanceRecord, read_record


@dataclass(frozen=True)
class Patience:
    """How long a start waits on the application holding its place, in seconds.

    ``record`` is the wait for a holder to say where it listens, ``silent`` the time a holder may
    leave its questions unanswered, ``quit`` the time a holder asked to quit, or seen closing, has
    to end, ``end_grace`` the time an ended process has before it is forced, and ``release`` the
    wait for the lock once the holder has been ended.
    """

    poll: float
    record: float
    silent: float
    quit: float
    end_grace: float
    release: float


@unique
class Intent(StrEnum):
    """What a start is for: running the application, or quitting the one that runs."""

    START = "start"
    QUIT = "quit"


@dataclass(frozen=True)
class Claimed:
    """The place is this start's: nothing else runs under its config."""

    lock: HeldLock


@dataclass(frozen=True)
class Running:
    """The same installation already runs under this config, at ``address``."""

    address: str


@dataclass(frozen=True)
class Refused:
    """The place stays taken, for the reason given."""

    reason: str


class Processes(Protocol):
    def is_running(self, identity: ProcessIdentity) -> bool: ...

    def end_tree(self, identity: ProcessIdentity, *, grace_seconds: float) -> None: ...


class Contact(Protocol):
    def reply(self, address: str) -> Reply: ...

    def ask_to_quit(self, address: str, *, seconds: float) -> None: ...


class Clock(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class _Watch:
    """What a start has seen of one holder: when it first saw it, asked it to quit, and saw it closing."""

    holder: ProcessIdentity
    first_seen: float
    asked_at: float | None
    closing_since: float | None

    def deadline(self, patience: Patience) -> float:
        """The moment the holder is ended at: once it has kept silent too long, or taken too long to quit."""
        deadline = self.first_seen + patience.silent
        for waiting_since in (self.asked_at, self.closing_since):
            if waiting_since is not None:
                deadline = max(deadline, waiting_since + patience.quit)
        return deadline


class Takeover:
    """How a start takes the place of the application running under its config.

    The lock at the place tells whether an application runs, and the record beside it where it
    listens and which process it is. A start opens the running application when it is the same
    installation, asks any other one to quit, and ends a holder that keeps silent or never quits,
    together with the processes it started. It ends only the process a record names and a check
    of its start time confirms, so a holder it cannot identify is left alone and the start refused.
    """

    def __init__(
        self, place: InstancePlace, *, patience: Patience, processes: Processes, contact: Contact, clock: Clock
    ) -> None:
        self._place = place
        self._patience = patience
        self._processes = processes
        self._contact = contact
        self._clock = clock

    def claim(self, intent: Intent) -> Claimed | Running | Refused:
        """Take the place for ``intent``, waiting for the application holding it to go where it has to.

        Raises:
            LockUnavailableError: the place's folder cannot hold a lock.
        """
        watch: _Watch | None = None
        unidentified_since: float | None = None
        while True:
            lock = try_lock(self._place.lock)
            if lock is not None:
                return Claimed(lock)
            now = self._clock.now()
            record = read_record(self._place.record)
            if record is None or not self._processes.is_running(record.process):
                unidentified_since = now if unidentified_since is None else unidentified_since
                if now - unidentified_since > self._patience.record:
                    return Refused(
                        f"Another start of SampleLibrary holds {self._place.lock} without saying where it runs."
                    )
                self._clock.sleep(self._patience.poll)
                continue
            unidentified_since = None
            if watch is None or watch.holder != record.process:
                watch = _Watch(holder=record.process, first_seen=now, asked_at=None, closing_since=None)
            answer = self._answer(record, watch, intent=intent, now=now)
            if isinstance(answer, Running):
                return answer
            watch = answer
            if self._clock.now() > watch.deadline(self._patience):
                return self._end(watch.holder)
            self._clock.sleep(self._patience.poll)

    def _answer(self, record: InstanceRecord, watch: _Watch, *, intent: Intent, now: float) -> _Watch | Running:
        """What the holder's answer calls for: opening it, asking it to quit, or waiting on it."""
        match self._contact.reply(record.address):
            case Reply.SAME_INSTALLATION if intent is Intent.START:
                return Running(record.address)
            case Reply.SAME_INSTALLATION | Reply.OTHER_INSTALLATION:
                if watch.asked_at is not None:
                    return watch
                self._contact.ask_to_quit(record.address, seconds=self._patience.quit)
                return replace(watch, asked_at=now)
            case Reply.CLOSED:
                return watch if watch.closing_since is not None else replace(watch, closing_since=now)
            case Reply.SILENT:
                return watch

    def _end(self, holder: ProcessIdentity) -> Claimed | Refused:
        """End the holder and the processes it started, then take the lock it leaves."""
        self._processes.end_tree(holder, grace_seconds=self._patience.end_grace)
        deadline = self._clock.now() + self._patience.release
        while True:
            lock = try_lock(self._place.lock)
            if lock is not None:
                return Claimed(lock)
            if self._clock.now() > deadline:
                return Refused("SampleLibrary kept running after it was closed. Restart the computer, then try again.")
            self._clock.sleep(self._patience.poll)
