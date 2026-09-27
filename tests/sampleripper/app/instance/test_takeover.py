from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Final

import pytest

from sampleripper.app.installation import Reply
from sampleripper.app.instance.lock import HeldLock, try_lock
from sampleripper.app.instance.place import InstancePlace
from sampleripper.app.instance.processes import ProcessIdentity
from sampleripper.app.instance.record import InstanceRecord, write_record
from sampleripper.app.instance.takeover import Claimed, Intent, Patience, Refused, Running, Takeover

PATIENCE: Final[Patience] = Patience(poll=0.25, record=10.0, silent=20.0, quit=120.0, end_grace=10.0, release=10.0)
FIRST_HOLDER: Final[ProcessIdentity] = ProcessIdentity(pid=4242, started_at=100.0)
SECOND_HOLDER: Final[ProcessIdentity] = ProcessIdentity(pid=4343, started_at=200.0)
FIRST_PORT: Final[int] = 27440
SECOND_PORT: Final[int] = 27441


class FakeClock:
    """Time that passes only while the takeover sleeps, running what a scene scheduled for each moment."""

    def __init__(self) -> None:
        self.moment = 0.0
        self._scheduled: list[tuple[float, Callable[[], None]]] = []

    def at(self, moment: float, action: Callable[[], None]) -> None:
        self._scheduled.append((moment, action))

    def now(self) -> float:
        return self.moment

    def sleep(self, seconds: float) -> None:
        self.moment += seconds
        due = [action for moment, action in self._scheduled if moment <= self.moment]
        self._scheduled = [(moment, action) for moment, action in self._scheduled if moment > self.moment]
        for action in due:
            action()


class Scene:
    """An application holding a start's place: its lock, its record, how it answers, and how it goes.

    The scene plays both the machine's processes and the holder's setup routes for the takeover.
    """

    def __init__(self, tmp_path: Path) -> None:
        self.place = InstancePlace(
            key="scene", directory=tmp_path / "place", log=tmp_path / "app.log", previous_log=tmp_path / "app.old.log"
        )
        self.clock = FakeClock()
        self.replies: dict[int, Reply] = {}
        self.running: set[ProcessIdentity] = set()
        self.quits_when_asked = False
        self.ends_when_ended = True
        self.asked: list[str] = []
        self.ended: list[ProcessIdentity] = []
        self._held: HeldLock | None = None

    def hold(self, identity: ProcessIdentity | None, *, port: int, reply: Reply) -> None:
        """Take the lock for a holder, recording ``identity`` as running on ``port``, or recording nothing."""
        if self._held is None:
            self._held = try_lock(self.place.lock)
        self.replies[port] = reply
        if identity is not None:
            self.record(identity, port=port)

    def record(self, identity: ProcessIdentity, *, port: int) -> None:
        self.running.add(identity)
        write_record(self.place.record, InstanceRecord(host="127.0.0.1", port=port, process=identity))

    def release(self) -> None:
        if self._held is not None:
            self._held.release()
            self._held = None
        self.running.clear()

    def claim(self, intent: Intent) -> Claimed | Running | Refused:
        return Takeover(self.place, patience=PATIENCE, processes=self, contact=self, clock=self.clock).claim(intent)

    def is_running(self, identity: ProcessIdentity) -> bool:
        return identity in self.running

    def end_tree(self, identity: ProcessIdentity, *, grace_seconds: float) -> None:
        self.ended.append(identity)
        if self.ends_when_ended:
            self.release()

    def reply(self, address: str) -> Reply:
        return self.replies[int(address.rstrip("/").rsplit(":", 1)[1])]

    def ask_to_quit(self, address: str, *, seconds: float) -> None:
        self.asked.append(address)
        if self.quits_when_asked:
            self.release()


@pytest.fixture
def scene(tmp_path: Path) -> Iterator[Scene]:
    played = Scene(tmp_path)
    yield played
    played.release()


def _address(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def _claimed(outcome: Claimed | Running | Refused) -> Claimed:
    assert isinstance(outcome, Claimed)
    outcome.lock.release()
    return outcome


def test_a_free_place_is_claimed_at_once(scene: Scene) -> None:
    _claimed(scene.claim(Intent.START))

    assert (scene.asked, scene.ended, scene.clock.moment) == ([], [], 0.0)


def test_the_same_installation_is_opened_where_it_runs(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.SAME_INSTALLATION)

    assert scene.claim(Intent.START) == Running(_address(FIRST_PORT))
    assert scene.asked == []


def test_another_installation_is_asked_once_to_quit_and_its_place_taken(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.OTHER_INSTALLATION)
    scene.clock.at(30.0, scene.release)

    _claimed(scene.claim(Intent.START))

    assert scene.asked == [_address(FIRST_PORT)]
    assert scene.ended == []


def test_quitting_asks_the_same_installation_to_quit(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.SAME_INSTALLATION)
    scene.quits_when_asked = True

    _claimed(scene.claim(Intent.QUIT))

    assert scene.asked == [_address(FIRST_PORT)]


def test_an_application_already_closing_is_given_time_to_end(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.CLOSED)
    scene.clock.at(PATIENCE.silent + 30.0, scene.release)

    _claimed(scene.claim(Intent.START))

    assert scene.ended == []


def test_an_application_that_stopped_answering_is_ended_and_its_place_taken(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.SILENT)

    _claimed(scene.claim(Intent.START))

    assert scene.ended == [FIRST_HOLDER]
    assert scene.clock.moment >= PATIENCE.silent


def test_an_application_that_never_quits_is_ended_once_its_time_to_quit_is_over(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.OTHER_INSTALLATION)

    _claimed(scene.claim(Intent.START))

    assert scene.asked == [_address(FIRST_PORT)]
    assert scene.ended == [FIRST_HOLDER]
    assert scene.clock.moment >= PATIENCE.quit


def test_a_holder_that_records_itself_late_is_found(scene: Scene) -> None:
    scene.hold(None, port=FIRST_PORT, reply=Reply.SAME_INSTALLATION)
    scene.clock.at(1.0, lambda: scene.record(FIRST_HOLDER, port=FIRST_PORT))

    assert scene.claim(Intent.START) == Running(_address(FIRST_PORT))


def test_a_holder_named_by_a_stale_record_is_left_alone_and_the_start_refused(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.SILENT)
    scene.running.clear()

    assert isinstance(scene.claim(Intent.START), Refused)
    assert scene.ended == []


def test_a_new_holder_is_given_its_own_time(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.SILENT)
    replaced_at = PATIENCE.silent - 5.0

    def replace_holder() -> None:
        scene.running.discard(FIRST_HOLDER)
        scene.hold(SECOND_HOLDER, port=SECOND_PORT, reply=Reply.SILENT)

    scene.clock.at(replaced_at, replace_holder)

    _claimed(scene.claim(Intent.START))

    assert scene.ended == [SECOND_HOLDER]
    assert scene.clock.moment >= replaced_at + PATIENCE.silent


def test_a_holder_that_outlives_its_end_keeps_the_place(scene: Scene) -> None:
    scene.hold(FIRST_HOLDER, port=FIRST_PORT, reply=Reply.SILENT)
    scene.ends_when_ended = False

    assert isinstance(scene.claim(Intent.START), Refused)
    assert scene.ended == [FIRST_HOLDER]
