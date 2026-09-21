from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from samplecore.models.morph import HeardMorphPoint
from samplemorph.routes.envelope import PreparedPair
from samplemorph.service.renderer import RenderBoundsError, load_renderer
from samplemorph.service.settings import MAXIMUM_RENDER_FRAMES, RenderLimits, ServiceSettings
from tests.samplemorph.service.conftest import StoredLibrary

FIRST_RATE_HZ = 8_363
SECOND_RATE_HZ = 16_726


@dataclass(frozen=True)
class _CountingPair:
    """A prepared pair that counts every render asked of it."""

    prepared: PreparedPair
    calls: list[int]

    @property
    def nbytes(self) -> int:
        return self.prepared.nbytes

    def render(self, *, weight: float) -> NDArray[np.float64]:
        self.calls.append(1)
        return self.prepared.render(weight=weight)


def test_the_fingerprint_follows_the_settings_the_route_renders_under(
    settings: ServiceSettings, gliding_settings: ServiceSettings
) -> None:
    held = load_renderer(settings)
    gliding = load_renderer(gliding_settings)

    assert held.fingerprint == load_renderer(settings).fingerprint
    assert held.fingerprint != gliding.fingerprint


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
    route = renderer._named.route  # pylint: disable=protected-access
    preparing = route.prepare_pair

    def counted(*arguments: Any, **options: Any) -> Any:
        prepared = preparing(*arguments, **options)
        return _CountingPair(prepared=prepared, calls=calls)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(type(route), "prepare_pair", lambda _route, *arguments, **options: counted(*arguments, **options))
        with ThreadPoolExecutor(max_workers=4) as pool:
            rendered = list(pool.map(renderer.render, [point] * 4))

    assert len(calls) == 1
    assert len(set(rendered)) == 1
