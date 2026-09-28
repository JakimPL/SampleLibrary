from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Final

import pytest
from PIL import Image

from tests.paths import FAVICON, ICONS_DIRECTORY, RENDER_ICONS_SCRIPT, SCRIPTS_DIRECTORY

# Where the logo's flat run, its tile and a corner sit, as fractions of the icon's width.
ON_THE_STROKE: Final[tuple[float, float]] = (6.5 / 32, 16 / 32)
ON_THE_TILE: Final[tuple[float, float]] = (16 / 32, 28 / 32)
IN_A_CORNER: Final[tuple[float, float]] = (0.5 / 32, 0.5 / 32)


def _load_render_icons() -> types.ModuleType:
    """Imports the script by file path, with the scripts folder on the path for its own `paths` module."""
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))
    try:
        spec = importlib.util.spec_from_file_location("render_icons", RENDER_ICONS_SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIRECTORY))
    return module


render_icons = _load_render_icons()


def _hex(color: tuple[int, ...]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color[:3])


def _sampled(path: Path) -> dict[str, str]:
    with Image.open(path) as image:
        pixels = image.convert("RGB")
        return {
            name: _hex(pixels.getpixel((round(x * pixels.width), round(y * pixels.height))))
            for name, (x, y) in (("stroke", ON_THE_STROKE), ("tile", ON_THE_TILE), ("corner", IN_A_CORNER))
        }


def _expected() -> dict[str, str]:
    logo = render_icons.Logo.read(FAVICON)
    return {"stroke": logo.stroke_color, "tile": logo.tile_color, "corner": render_icons.CORNER_COLOR}


def test_the_icons_are_drawn_from_the_logo_at_every_size(tmp_path: Path) -> None:
    written = render_icons.render_icons(FAVICON, tmp_path)

    assert [path.name for path in written] == list(render_icons.ICON_SIZES)
    for path in written:
        with Image.open(path) as image:
            assert image.size == (render_icons.ICON_SIZES[path.name],) * 2
        assert _sampled(path) == _expected()


@pytest.mark.parametrize("name", list(render_icons.ICON_SIZES))
def test_the_committed_icons_keep_step_with_the_logo(name: str) -> None:
    """A recolored logo is followed by `just icons`, which these files then reflect."""
    assert _sampled(ICONS_DIRECTORY / name) == _expected()


def test_the_logo_path_is_read_as_its_vertices() -> None:
    logo = render_icons.Logo.read(FAVICON)

    assert logo.points[0] == (5.0, 16.0)
    assert logo.points[-1] == (27.0, 16.0)
    assert len(logo.points) == 9


def test_a_path_drawn_with_curves_is_refused() -> None:
    with pytest.raises(ValueError, match="commands this renderer does not know"):
        render_icons._path_points("M5 16c1 1 2 2 3 3")  # pylint: disable=protected-access
