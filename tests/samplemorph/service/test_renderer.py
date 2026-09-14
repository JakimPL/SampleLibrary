from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from samplecore.models.morph import HeardMorphPoint
from samplemorph.canonicalizers.log_frequency import linear_axis_inverse
from samplemorph.geometry import log_frequency_geometry
from samplemorph.model_store import DEFAULT_MODEL_NAME, load_model, model_path, save_model
from samplemorph.service import renderer as renderer_module
from samplemorph.service.renderer import RenderBoundsError, load_renderer
from samplemorph.service.settings import MAXIMUM_RENDER_FRAMES, RenderLimits, ServiceSettings
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


def test_the_fingerprint_follows_the_bytes_of_the_model_it_was_loaded_from(
    settings: ServiceSettings, library: StoredLibrary, tmp_path: Path
) -> None:
    before = load_renderer(settings).fingerprint
    root = tmp_path / "library"
    shutil.copytree(library.root, root)
    copied = replace(settings, library_root=root)
    stored = model_path(root, name=DEFAULT_MODEL_NAME)
    loaded = load_model(stored)
    save_model(stored, replace(loaded, description=loaded.description.model_copy(update={"random_seed": 7})))

    assert load_renderer(copied).fingerprint != before


def test_a_process_rendering_on_the_processor_says_so(settings: ServiceSettings) -> None:
    assert load_renderer(settings).status().device == "cpu"


@pytest.mark.parametrize(
    ("first_rate_hz", "second_rate_hz", "maximum_frames", "reason"),
    [
        (1_000, 32_000, MAXIMUM_RENDER_FRAMES, "32.0 times apart"),
        (FIRST_RATE_HZ, SECOND_RATE_HZ, 1_024, "past the 1024"),
    ],
    ids=("rates too far apart", "a render too long"),
)
def test_a_point_past_the_process_limits_is_refused_before_it_renders(
    settings: ServiceSettings,
    library: StoredLibrary,
    first_rate_hz: int,
    second_rate_hz: int,
    maximum_frames: int,
    reason: str,
) -> None:
    renderer = load_renderer(replace(settings, limits=RenderLimits(maximum_frames=maximum_frames)))
    point = HeardMorphPoint(
        first=library.hashes[0],
        second=library.hashes[1],
        weight=0.5,
        first_rate_hz=first_rate_hz,
        second_rate_hz=second_rate_hz,
    )

    with pytest.raises(RenderBoundsError, match=reason):
        renderer.check_bounds(point)


def test_identical_points_asked_for_at_once_render_once(settings: ServiceSettings, library: StoredLibrary) -> None:
    renderer = load_renderer(settings)
    point = HeardMorphPoint(
        first=library.hashes[0],
        second=library.hashes[2],
        weight=0.5,
        first_rate_hz=FIRST_RATE_HZ,
        second_rate_hz=FIRST_RATE_HZ,
    )
    calls: list[int] = []
    rendering = renderer_module.render_morph

    def counted(*arguments: Any, **options: Any) -> Any:
        calls.append(1)
        return rendering(*arguments, **options)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(renderer_module, "render_morph", counted)
        with ThreadPoolExecutor(max_workers=4) as pool:
            rendered = list(pool.map(renderer.render, [point] * 4))

    assert len(calls) == 1
    assert len(set(rendered)) == 1
