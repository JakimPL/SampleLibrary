from __future__ import annotations

from samplecore.ports import ANY_PORT
from samplelibrary.app.instance.processes import ProcessIdentity
from samplelibrary.app.instance.record import InstanceRecord
from samplelibrary.app.listener import APPLICATION_PORT_CHOICES, FIRST_APPLICATION_PORT, port_choices

FIXED_PORTS = tuple(range(FIRST_APPLICATION_PORT, FIRST_APPLICATION_PORT + APPLICATION_PORT_CHOICES))


def _record(port: int) -> InstanceRecord:
    return InstanceRecord(host="127.0.0.1", port=port, process=ProcessIdentity(pid=1, started_at=0.0))


def test_a_port_a_person_asks_for_is_the_only_choice() -> None:
    assert port_choices(8123, _record(30000)) == (8123,)


def test_a_first_start_tries_the_fixed_ports_then_any() -> None:
    assert port_choices(None, None) == (*FIXED_PORTS, ANY_PORT)


def test_a_later_start_tries_the_port_it_listened_on_last_first() -> None:
    assert port_choices(None, _record(30000)) == (30000, *FIXED_PORTS, ANY_PORT)


def test_a_remembered_port_among_the_fixed_ones_is_tried_once() -> None:
    remembered = FIXED_PORTS[3]

    assert port_choices(None, _record(remembered)) == (
        remembered,
        *(port for port in FIXED_PORTS if port != remembered),
        ANY_PORT,
    )
