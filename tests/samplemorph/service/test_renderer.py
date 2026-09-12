from __future__ import annotations

from samplecore.models.morph import MorphPoint
from samplemorph.canonicalizers.log_frequency import linear_axis_inverse
from samplemorph.geometry import log_frequency_geometry
from samplemorph.service.renderer import load_renderer
from samplemorph.service.settings import ServiceSettings
from tests.samplemorph.service.conftest import StoredLibrary


def test_the_fingerprint_follows_the_models_the_route_renders_through(
    settings: ServiceSettings, restored_settings: ServiceSettings
) -> None:
    integrating = load_renderer(settings)
    restored = load_renderer(restored_settings)

    assert integrating.fingerprint == load_renderer(settings).fingerprint
    assert integrating.fingerprint != restored.fingerprint


def test_a_validator_names_one_point_under_one_model(settings: ServiceSettings, library: StoredLibrary) -> None:
    renderer = load_renderer(settings)
    halfway = MorphPoint(first=library.hashes[0], second=library.hashes[1], weight=0.5)
    quarter = MorphPoint(first=library.hashes[0], second=library.hashes[1], weight=0.25)
    reversed_pair = MorphPoint(first=library.hashes[1], second=library.hashes[0], weight=0.5)

    assert renderer.etag(halfway) == renderer.etag(halfway)
    assert renderer.etag(halfway) != renderer.etag(quarter)
    assert renderer.etag(halfway) != renderer.etag(reversed_pair)


def test_warming_up_leaves_the_band_matrix_inverse_in_the_cache(settings: ServiceSettings) -> None:
    load_renderer(settings)

    assert linear_axis_inverse.cache_info().currsize >= 1
    assert linear_axis_inverse(log_frequency_geometry()) is linear_axis_inverse(log_frequency_geometry())
