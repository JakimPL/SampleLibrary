from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from xml.etree import ElementTree

from paths import FAVICON, ICONS_DIRECTORY
from PIL import Image, ImageDraw

SVG_NAMESPACE: Final[str] = "{http://www.w3.org/2000/svg}"
# The web page's own color, painted outside the rounded tile: the icons fill their square.
CORNER_COLOR: Final[str] = "#e9ebf0"
SUPERSAMPLING: Final[int] = 8
ICON_SIZES: Final[dict[str, int]] = {"icon-512.png": 512, "icon-192.png": 192, "apple-touch-icon.png": 180}
PATH_COMMAND: Final[re.Pattern[str]] = re.compile(r"([MLHVmlhv])([^A-Za-z]*)")


@dataclass(frozen=True)
class Logo:
    """The logo as `favicon.svg` draws it: a rounded tile of ``size`` units, and a stroke along ``points``."""

    size: float
    corner_radius: float
    tile_color: str
    points: tuple[tuple[float, float], ...]
    stroke_color: str
    stroke_width: float

    @classmethod
    def read(cls, path: Path) -> Logo:
        """Read the logo from its SVG source, whose one rect is the tile and whose one path is the stroke."""
        root = ElementTree.parse(path).getroot()
        rect = root.find(f"{SVG_NAMESPACE}rect")
        stroke = root.find(f"{SVG_NAMESPACE}path")
        if rect is None or stroke is None:
            raise ValueError(f"{path} holds no rect and path to draw the logo from")
        return cls(
            size=float(rect.attrib["width"]),
            corner_radius=float(rect.attrib["rx"]),
            tile_color=rect.attrib["fill"],
            points=_path_points(stroke.attrib["d"]),
            stroke_color=stroke.attrib["stroke"],
            stroke_width=float(stroke.attrib["stroke-width"]),
        )

    def render(self, pixels: int) -> Image.Image:
        """Draw the logo ``pixels`` wide, at a larger size first so the edges come out smooth."""
        canvas = pixels * SUPERSAMPLING
        scale = canvas / self.size
        image = Image.new("RGB", (canvas, canvas), CORNER_COLOR)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius=self.corner_radius * scale, fill=self.tile_color)
        scaled = [(x * scale, y * scale) for x, y in self.points]
        width = self.stroke_width * scale
        draw.line(scaled, fill=self.stroke_color, width=round(width), joint="curve")
        for x, y in (scaled[0], scaled[-1]):
            draw.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=self.stroke_color)
        return image.resize((pixels, pixels), Image.Resampling.LANCZOS)


def render_icons(source: Path, directory: Path) -> tuple[Path, ...]:
    """Write every PNG icon of the web app into ``directory``, drawn from the logo at ``source``."""
    logo = Logo.read(source)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, pixels in ICON_SIZES.items():
        target = directory / name
        logo.render(pixels).save(target, format="PNG")
        written.append(target)
    return tuple(written)


def _path_points(data: str) -> tuple[tuple[float, float], ...]:
    """The vertices of a path drawn with move, line, horizontal and vertical commands, absolute or relative.

    Raises:
        ValueError: the path uses a command beyond those, such as a curve.
    """
    if PATH_COMMAND.sub("", data).strip():
        raise ValueError(f"the path {data!r} draws with commands this renderer does not know")
    points: list[tuple[float, float]] = []
    x = y = 0.0
    for command, arguments in PATH_COMMAND.findall(data):
        numbers = [float(number) for number in re.findall(r"-?\d*\.?\d+", arguments)]
        relative = command.islower()
        match command.upper():
            case "M" | "L":
                for dx, dy in zip(numbers[::2], numbers[1::2], strict=True):
                    x, y = (x + dx, y + dy) if relative else (dx, dy)
                    points.append((x, y))
            case "H":
                for dx in numbers:
                    x = x + dx if relative else dx
                    points.append((x, y))
            case "V":
                for dy in numbers:
                    y = y + dy if relative else dy
                    points.append((x, y))
    return tuple(points)


def main() -> None:
    """Render the web app's PNG icons from `favicon.svg`, which the installers' icons are cut from in turn."""
    for path in render_icons(FAVICON, ICONS_DIRECTORY):
        print(f"Wrote {path}.")


if __name__ == "__main__":
    main()
