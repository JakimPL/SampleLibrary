from __future__ import annotations

from samplecore.models.morph import HeardMorphPoint
from samplemorph.canonicalizers.log_frequency import linear_axis_inverse
from samplemorph.geometry import log_frequency_geometry
from samplemorph.service.renderer import load_renderer
from samplemorph.service.settings import ServiceSettings
from tests.samplemorph.service.conftest import StoredLibrary

FIRST_RATE_HZ = 8_363
SECOND_RATE_HZ = 16_726


def test_the_fingerprint_follows_the_models_the_route_renders_through(
    settings: ServiceSettings, restored_settings: ServiceSettings
) -> None:
    integrating = load_renderer(settings)
    restored = load_renderer(restored_settings)

    assert integrating.fingerprint == load_renderer(settings).fingerprint
    assert integrating.fingerprint != restored.fingerprint


def test_a_validator_names_one_point_under_one_model_at_one_pair_of_rates(
    settings: ServiceSettings, library: StoredLibrary
) -> None:
    renderer = load_renderer(settings)
    first, second = library.hashes[0], library.hashes[1]
    halfway = HeardMorphPoint(
        first=first, second=second, weight=0.5, first_rate_hz=FIRST_RATE_HZ, second_rate_hz=SECOND_RATE_HZ
    )
    quarter = HeardMorphPoint(
        first=first, second=second, weight=0.25, first_rate_hz=FIRST_RATE_HZ, second_rate_hz=SECOND_RATE_HZ
    )
    reversed_pair = HeardMorphPoint(
        first=second, second=first, weight=0.5, first_rate_hz=SECOND_RATE_HZ, second_rate_hz=FIRST_RATE_HZ
    )
    retuned = HeardMorphPoint(
        first=first, second=second, weight=0.5, first_rate_hz=FIRST_RATE_HZ, second_rate_hz=FIRST_RATE_HZ
    )

    assert renderer.etag(halfway) == renderer.etag(halfway)
    assert renderer.etag(halfway) != renderer.etag(quarter)
    assert renderer.etag(halfway) != renderer.etag(reversed_pair)
    assert renderer.etag(halfway) != renderer.etag(retuned)


def test_warming_up_leaves_the_band_matrix_inverse_in_the_cache(settings: ServiceSettings) -> None:
    load_renderer(settings)

    assert linear_axis_inverse.cache_info().currsize >= 1
    assert linear_axis_inverse(log_frequency_geometry()) is linear_axis_inverse(log_frequency_geometry())
