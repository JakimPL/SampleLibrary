from __future__ import annotations

import json
from pathlib import Path

import pytest

from sampleserver.app import API_PREFIX
from sampleserver.openapi_export import main

PROGRAM = "samplelibrary schema"


def test_main_prints_a_valid_openapi_document(capsys: pytest.CaptureFixture[str]) -> None:
    main([], prog=PROGRAM)

    schema = json.loads(capsys.readouterr().out)

    assert "openapi" in schema
    assert f"{API_PREFIX}/modules" in schema["paths"]


def test_main_writes_the_same_document_to_a_named_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "openapi.json"
    main([], prog=PROGRAM)
    printed = capsys.readouterr().out

    main(["--output", str(output)], prog=PROGRAM)

    assert output.read_text(encoding="utf-8") == printed
    assert capsys.readouterr().out == ""


def test_writing_into_a_directory_that_is_not_there_ends_with_one_message(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--output", str(tmp_path / "absent" / "openapi.json")], prog=PROGRAM)

    assert "Wrote nothing" in str(raised.value.code)
