from __future__ import annotations

import io
import shutil
from dataclasses import replace
from http import HTTPStatus
from pathlib import Path

import numpy as np
import pytest
import soundfile
from fastapi.testclient import TestClient

from samplecore.models.morph import MORPH_WEIGHT_STEPS, HeardMorphPoint
from samplecore.storage import audio_store
from samplemorph.canonicalizers.common import analysis_transform
from samplemorph.envelope.filtering import filtered_waveform
from samplemorph.envelope.payload import response_from_payload
from samplemorph.envelope.response import HeldEnd
from samplemorph.envelope.settings import EnvelopeSettings, Timeline
from samplemorph.geometry import log_frequency_geometry
from samplemorph.model_store import MODELS_DIRECTORY_NAME, PRINCIPAL_COMPONENT_CODEC_NAME
from samplemorph.registries import PGHI_VOCODER_NAME
from samplemorph.rendering import FULL_SCALE_CEILING
from samplemorph.routes.kinds import RouteKind
from samplemorph.routes.route import hear_in_frame
from samplemorph.routes.selection import PROCESSOR
from samplemorph.service.app import create_app
from samplemorph.service.renderer import MorphRenderer, load_renderer
from samplemorph.service.settings import RESPONSE_MEDIA_TYPE, ServiceSettings
from tests.samplemorph.service.conftest import StoredLibrary

AUDIO_PATH = "/morph/audio"
RESPONSE_PATH = "/morph/response"
STATUS_PATH = "/morph/status"
DIGEST_LENGTH = 64
FIRST_RATE_HZ = 8_363
SECOND_RATE_HZ = 16_726
SOUND_TOLERANCE = 1e-6


def _renderer(client: TestClient) -> MorphRenderer:
    renderer: MorphRenderer = client.app.state.renderer
    return renderer


def _params(library: StoredLibrary, weight: float) -> dict[str, str | float | int]:
    return {
        "first": library.hashes[0],
        "second": library.hashes[1],
        "weight": weight,
        "first_rate_hz": FIRST_RATE_HZ,
        "second_rate_hz": SECOND_RATE_HZ,
    }


def test_the_status_names_what_the_process_serves(client: TestClient) -> None:
    status = client.get(STATUS_PATH).json()

    assert status["route"] == status["name"] == RouteKind.LATENT.value
    assert status["description"]["model"]["codec"] == PRINCIPAL_COMPONENT_CODEC_NAME
    assert status["description"]["vocoder"] == PGHI_VOCODER_NAME
    assert status["description"]["restorer"] is None
    assert status["device"] == PROCESSOR
    assert status["weight_steps"] == MORPH_WEIGHT_STEPS
    assert len(status["fingerprint"]) == DIGEST_LENGTH


def test_the_envelope_route_renders_end_to_end_reading_no_stored_model(
    envelope_settings: ServiceSettings, library: StoredLibrary, tmp_path: Path
) -> None:
    root = tmp_path / "library"
    shutil.copytree(library.root, root, ignore=shutil.ignore_patterns(MODELS_DIRECTORY_NAME))
    with TestClient(create_app(load_renderer(replace(envelope_settings, library_root=root)))) as client:
        status = client.get(STATUS_PATH).json()
        response = client.get(AUDIO_PATH, params=_params(library, 0.5))

    assert status["route"] == RouteKind.ENVELOPE.value
    served = envelope_settings.selection.envelope
    assert status["name"] == f"{RouteKind.ENVELOPE.value}-{served.excitation.value}"
    assert status["description"]["envelope_settings"] == served.model_dump(mode="json")
    assert response.status_code == 200
    assert soundfile.read(io.BytesIO(response.content))[1] == SECOND_RATE_HZ


def test_a_point_renders_as_a_wav_at_the_rate_the_pair_is_heard_at_with_its_caching_headers(
    client: TestClient, library: StoredLibrary
) -> None:
    response = client.get(AUDIO_PATH, params=_params(library, 0.5))

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["etag"].startswith('"')
    assert response.headers["cache-control"] == "private, no-cache"
    frames, rate = soundfile.read(io.BytesIO(response.content))
    assert rate == SECOND_RATE_HZ
    assert frames.shape[0] > 0
    assert float(np.abs(frames).max()) < 1.0


def test_the_endpoints_sound_for_their_own_heard_length(client: TestClient, library: StoredLibrary) -> None:
    """The slower sample gains frames on its way into the pair's frame, and sounds as long as before."""
    first, first_rate = soundfile.read(io.BytesIO(client.get(AUDIO_PATH, params=_params(library, 0.0)).content))
    second, second_rate = soundfile.read(io.BytesIO(client.get(AUDIO_PATH, params=_params(library, 1.0)).content))

    assert first.shape[0] / first_rate == pytest.approx(library.frame_counts[0] / FIRST_RATE_HZ)
    assert second.shape[0] / second_rate == pytest.approx(library.frame_counts[1] / SECOND_RATE_HZ)


def test_a_weight_off_the_grid_is_refused(client: TestClient, library: StoredLibrary) -> None:
    assert client.get(AUDIO_PATH, params=_params(library, 0.305)).status_code == 422


def test_a_point_asked_for_without_its_rates_is_refused(client: TestClient, library: StoredLibrary) -> None:
    params = {"first": library.hashes[0], "second": library.hashes[1], "weight": 0.5}

    assert client.get(AUDIO_PATH, params=params).status_code == 422


def test_a_sample_the_store_lacks_is_reported(client: TestClient, library: StoredLibrary) -> None:
    response = client.get(AUDIO_PATH, params={**_params(library, 0.5), "second": "f" * 64})

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


def test_a_pair_is_prepared_once_however_many_weights_are_asked_for(client: TestClient, library: StoredLibrary) -> None:
    for step in range(0, MORPH_WEIGHT_STEPS + 1, MORPH_WEIGHT_STEPS // 4):
        assert client.get(AUDIO_PATH, params=_params(library, step / MORPH_WEIGHT_STEPS)).status_code == 200

    assert _renderer(client).pair_count == 1
    assert _renderer(client).render_count == 5


def test_the_restored_route_renders_end_to_end(restored_settings: ServiceSettings, library: StoredLibrary) -> None:
    with TestClient(create_app(load_renderer(restored_settings))) as client:
        status = client.get(STATUS_PATH).json()
        response = client.get(AUDIO_PATH, params=_params(library, 0.5))

    assert status["description"]["restorer"] is not None
    assert response.status_code == 200
    assert soundfile.read(io.BytesIO(response.content))[1] == SECOND_RATE_HZ


@pytest.mark.parametrize(
    "condition",
    ['"stale", {etag}', "W/{etag}", "*"],
    ids=("a list naming it", "a weak tag", "any tag"),
)
def test_every_form_of_a_matching_validator_is_answered_without_rendering(
    client: TestClient, library: StoredLibrary, condition: str
) -> None:
    etag = _renderer(client).etag(HeardMorphPoint.model_validate(_params(library, 0.75)))
    rendered = _renderer(client).render_count

    response = client.get(
        AUDIO_PATH, params=_params(library, 0.75), headers={"If-None-Match": condition.format(etag=etag)}
    )

    assert response.status_code == 304
    assert _renderer(client).render_count == rendered


def test_a_point_past_the_process_limits_is_refused(client: TestClient, library: StoredLibrary) -> None:
    response = client.get(
        AUDIO_PATH, params={**_params(library, 0.5), "first_rate_hz": 1_000, "second_rate_hz": 32_000}
    )

    assert response.status_code == 422
    assert "times apart" in response.json()["detail"]


def test_a_quiet_point_keeps_its_level(client: TestClient, library: StoredLibrary) -> None:
    """A render is lowered only to keep from clipping, so two quiet ends stay quiet between them."""
    frames, _ = soundfile.read(io.BytesIO(client.get(AUDIO_PATH, params=_params(library, 0.5)).content))

    assert float(np.abs(frames).max()) <= FULL_SCALE_CEILING + 1.0 / 32768


def test_an_end_found_in_a_sample_directory_renders_from_its_file(client: TestClient, library: StoredLibrary) -> None:
    params = {**_params(library, 0.5), "second": library.file_hash, "second_file": str(library.file_path)}

    response = client.get(AUDIO_PATH, params=params)

    assert response.status_code == 200
    assert soundfile.read(io.BytesIO(response.content))[1] == SECOND_RATE_HZ


def test_a_file_outside_every_served_sample_directory_is_refused(
    client: TestClient, library: StoredLibrary, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere.wav"
    elsewhere.write_bytes(library.file_path.read_bytes())
    climbing = library.sample_directory / ".." / elsewhere.name

    for named in (elsewhere, climbing):
        params = {**_params(library, 0.5), "second": library.file_hash, "second_file": str(named)}
        response = client.get(AUDIO_PATH, params=params)

        assert response.status_code == 404
        assert "no sample directory" in response.json()["detail"]


def test_a_file_holding_another_sample_than_the_one_named_is_refused(
    client: TestClient, library: StoredLibrary
) -> None:
    params = {**_params(library, 0.5), "second": library.hashes[2], "second_file": str(library.file_path)}

    response = client.get(AUDIO_PATH, params=params)

    assert response.status_code == 404
    assert "holds another sample" in response.json()["detail"]


def _pair_params(library: StoredLibrary) -> dict[str, str | float | int]:
    return {
        "first": library.hashes[0],
        "second": library.hashes[1],
        "first_rate_hz": FIRST_RATE_HZ,
        "second_rate_hz": SECOND_RATE_HZ,
    }


def test_a_pair_answers_with_the_filter_between_its_two_samples(
    envelope_settings: ServiceSettings, library: StoredLibrary
) -> None:
    with TestClient(create_app(load_renderer(envelope_settings))) as client:
        answered = client.get(RESPONSE_PATH, params=_pair_params(library))

        assert answered.status_code == HTTPStatus.OK
        assert answered.headers["content-type"] == RESPONSE_MEDIA_TYPE
        response = response_from_payload(answered.content)
        assert response.description.rate_hz == max(FIRST_RATE_HZ, SECOND_RATE_HZ)
        assert response.first.held is HeldEnd.FIRST
        assert response.second.held is HeldEnd.SECOND


def test_a_pair_asked_for_twice_is_read_once(envelope_settings: ServiceSettings, library: StoredLibrary) -> None:
    with TestClient(create_app(load_renderer(envelope_settings))) as client:
        for _ in range(2):
            client.get(RESPONSE_PATH, params=_pair_params(library))

        assert _renderer(client).response_count == 1


def test_a_caller_holding_the_filter_is_answered_without_reading_it_again(
    envelope_settings: ServiceSettings, library: StoredLibrary
) -> None:
    with TestClient(create_app(load_renderer(envelope_settings))) as client:
        first = client.get(RESPONSE_PATH, params=_pair_params(library))

        again = client.get(
            RESPONSE_PATH, params=_pair_params(library), headers={"If-None-Match": first.headers["etag"]}
        )

        assert again.status_code == HTTPStatus.NOT_MODIFIED
        assert again.content == b""


def test_a_process_serving_another_route_says_it_holds_no_filter(
    settings: ServiceSettings, library: StoredLibrary
) -> None:
    with TestClient(create_app(load_renderer(settings))) as client:
        answered = client.get(RESPONSE_PATH, params=_pair_params(library))

        assert answered.status_code == HTTPStatus.CONFLICT
        assert "filter" in answered.json()["detail"]


def test_a_pair_naming_a_sample_the_store_lacks_is_refused(
    envelope_settings: ServiceSettings, library: StoredLibrary
) -> None:
    with TestClient(create_app(load_renderer(envelope_settings))) as client:
        answered = client.get(RESPONSE_PATH, params={**_pair_params(library), "second": "f" * DIGEST_LENGTH})

        assert answered.status_code == HTTPStatus.NOT_FOUND


def test_the_filter_a_pair_answers_with_returns_that_sample_as_the_pair_hears_it(
    envelope_settings: ServiceSettings, library: StoredLibrary
) -> None:
    held_to_first = replace(
        envelope_settings,
        selection=envelope_settings.selection.model_copy(
            update={"envelope": EnvelopeSettings(timeline=Timeline.FIRST)}
        ),
    )
    with TestClient(create_app(load_renderer(held_to_first))) as client:
        response = response_from_payload(client.get(RESPONSE_PATH, params=_pair_params(library)).content)

    heard = hear_in_frame(
        audio_store.read_object(library.root, library.hashes[0]).pcm,
        rate_hz=float(FIRST_RATE_HZ),
        target_rate_hz=response.description.rate_hz,
    )
    geometry = log_frequency_geometry()

    filtered = filtered_waveform(
        analysis_transform(heard.mono, geometry=geometry), response.first, weight=0.0, geometry=geometry
    )

    np.testing.assert_allclose(filtered, heard.mono, atol=SOUND_TOLERANCE)
