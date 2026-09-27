from __future__ import annotations

import json
from pathlib import Path

import pytest

from samplelibrary.app.instance.processes import ProcessIdentity
from samplelibrary.app.instance.record import InstanceRecord, read_record, write_record

RECORD = InstanceRecord(host="127.0.0.1", port=27440, process=ProcessIdentity(pid=4321, started_at=1790000000.25))


def test_a_record_reads_back_as_it_was_written(tmp_path: Path) -> None:
    path = tmp_path / "instance.json"

    write_record(path, RECORD)

    assert read_record(path) == RECORD


def test_a_record_from_a_later_version_reads_past_the_fields_it_adds(tmp_path: Path) -> None:
    path = tmp_path / "instance.json"
    content = RECORD.model_dump(mode="json")
    content["added_later"] = True
    content["process"]["also_added"] = 1
    path.write_text(json.dumps(content), encoding="utf-8")

    assert read_record(path) == RECORD


@pytest.mark.parametrize("content", [None, "{not json", '{"host": "127.0.0.1"}'], ids=("missing", "broken", "partial"))
def test_a_record_that_cannot_be_read_reads_as_none(tmp_path: Path, content: str | None) -> None:
    path = tmp_path / "instance.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    assert read_record(path) is None


@pytest.mark.parametrize(
    ("host", "address"),
    [("127.0.0.1", "http://127.0.0.1:27440/"), ("::1", "http://[::1]:27440/")],
    ids=("IPv4", "IPv6"),
)
def test_a_record_names_the_address_a_browser_opens(host: str, address: str) -> None:
    assert RECORD.model_copy(update={"host": host}).address == address
