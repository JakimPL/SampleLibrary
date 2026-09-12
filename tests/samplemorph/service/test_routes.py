from __future__ import annotations

import io

import numpy as np
import soundfile
from fastapi.testclient import TestClient

from samplecore.models.morph import MORPH_WEIGHT_STEPS
from samplecore.storage.audio_store import NOMINAL_WAV_RATE
from samplemorph.model_store import DEFAULT_MODEL_NAME
from samplemorph.registries import PGHI_VOCODER_NAME
from samplemorph.service.app import create_app
from samplemorph.service.renderer import MorphRenderer
from samplemorph.service.settings import DEFAULT_INFERENCE_DEVICE, ServiceSettings
from tests.samplemorph.service.conftest import StoredLibrary

AUDIO_PATH = "/morph/audio"
STATUS_PATH = "/morph/status"
DIGEST_LENGTH = 64


def _renderer(client: TestClient) -> MorphRenderer:
    renderer: MorphRenderer = client.app.state.renderer
    return renderer


def _params(library: StoredLibrary, weight: float) -> dict[str, str | float]:
    return {"first": library.hashes[0], "second": library.hashes[1], "weight": weight}


def test_the_status_names_what_the_process_serves(client: TestClient) -> None:
    status = client.get(STATUS_PATH).json()

    assert status["model"] == DEFAULT_MODEL_NAME
    assert status["vocoder"] == PGHI_VOCODER_NAME
    assert status["restorer"] is None
    assert status["device"] == DEFAULT_INFERENCE_DEVICE
    assert status["weight_steps"] == MORPH_WEIGHT_STEPS
    assert len(status["fingerprint"]) == DIGEST_LENGTH


def test_a_point_renders_as_a_wav_at_the_nominal_rate_with_its_caching_headers(
    client: TestClient, library: StoredLibrary
) -> None:
    response = client.get(AUDIO_PATH, params=_params(library, 0.5))

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["etag"].startswith('"')
    assert "max-age" in response.headers["cache-control"]
    frames, rate = soundfile.read(io.BytesIO(response.content))
    assert rate == NOMINAL_WAV_RATE
    assert frames.shape[0] > 0
    assert float(np.abs(frames).max()) < 1.0


def test_the_endpoints_sound_for_their_own_sample_s_length(client: TestClient, library: StoredLibrary) -> None:
    first = soundfile.read(io.BytesIO(client.get(AUDIO_PATH, params=_params(library, 0.0)).content))[0]
    second = soundfile.read(io.BytesIO(client.get(AUDIO_PATH, params=_params(library, 1.0)).content))[0]

    assert first.shape[0] == library.frame_counts[0]
    assert second.shape[0] == library.frame_counts[1]


def test_a_weight_off_the_grid_is_refused(client: TestClient, library: StoredLibrary) -> None:
    assert client.get(AUDIO_PATH, params=_params(library, 0.3)).status_code == 422


def test_a_sample_the_store_lacks_is_reported(client: TestClient, library: StoredLibrary) -> None:
    response = client.get(AUDIO_PATH, params={"first": library.hashes[0], "second": "f" * 64, "weight": 0.5})

    assert response.status_code == 404
    assert "no object is stored" in response.json()["detail"]


def test_a_render_the_caller_holds_is_answered_without_rendering_again(
    client: TestClient, library: StoredLibrary
) -> None:
    first = client.get(AUDIO_PATH, params=_params(library, 0.25))
    rendered = _renderer(client).render_count

    again = client.get(AUDIO_PATH, params=_params(library, 0.25), headers={"If-None-Match": first.headers["etag"]})

    assert again.status_code == 304
    assert again.headers["etag"] == first.headers["etag"]
    assert _renderer(client).render_count == rendered


def test_a_pair_is_encoded_once_however_many_weights_are_asked_for(client: TestClient, library: StoredLibrary) -> None:
    for step in range(0, MORPH_WEIGHT_STEPS + 1, MORPH_WEIGHT_STEPS // 4):
        assert client.get(AUDIO_PATH, params=_params(library, step / MORPH_WEIGHT_STEPS)).status_code == 200

    assert _renderer(client).latent_count == 2
    assert _renderer(client).render_count == 5


def test_the_restored_route_renders_end_to_end(restored_settings: ServiceSettings, library: StoredLibrary) -> None:
    with TestClient(create_app(restored_settings)) as client:
        status = client.get(STATUS_PATH).json()
        response = client.get(AUDIO_PATH, params=_params(library, 0.5))

    assert status["restorer"] is not None
    assert response.status_code == 200
    assert soundfile.read(io.BytesIO(response.content))[1] == NOMINAL_WAV_RATE
