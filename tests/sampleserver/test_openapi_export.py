from __future__ import annotations

import json

import pytest

from sampleserver.openapi_export import main


def test_main_prints_a_valid_openapi_document(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    schema = json.loads(capsys.readouterr().out)

    assert "openapi" in schema
    assert "/modules" in schema["paths"]
