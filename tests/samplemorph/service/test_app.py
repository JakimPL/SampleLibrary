from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from samplemorph.model_store import DEFAULT_MODEL_NAME
from samplemorph.pipeline import RouteChoice
from samplemorph.registries import DEFAULT_MORPHER_NAME, PGHI_VOCODER_NAME
from samplemorph.service.app import create_app
from samplemorph.service.settings import DEFAULT_INFERENCE_DEVICE, ServiceSettings
from samplemorph.vocoders.restored import DEFAULT_RESTORER_NAME


def test_starting_over_a_library_with_no_model_fails_at_startup(tmp_path: Path) -> None:
    settings = ServiceSettings(
        library_root=tmp_path,
        choice=RouteChoice(
            model_name=DEFAULT_MODEL_NAME,
            vocoder_name=PGHI_VOCODER_NAME,
            restorer_name=DEFAULT_RESTORER_NAME,
            morpher_name=DEFAULT_MORPHER_NAME,
            device=DEFAULT_INFERENCE_DEVICE,
        ),
    )

    with pytest.raises(FileNotFoundError):
        with TestClient(create_app(settings)):
            pass
