from __future__ import annotations

import json

import pytest

from sampleserver.app import API_PREFIX
from sampleserver.openapi_export import main

PROGRAM = "samplelibrary schema"


def test_main_prints_a_valid_openapi_document(capsys: pytest.CaptureFixture[str]) -> None:
    main([], prog=PROGRAM)

    schema = json.loads(capsys.readouterr().out)

    assert "openapi" in schema
    assert f"{API_PREFIX}/modules" in schema["paths"]
