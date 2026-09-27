from __future__ import annotations

from pathlib import Path
from typing import Final

from paths import APP_ICON
from PIL import Image, ImageDraw

CORNER_RADIUS_FRACTION: Final[float] = 7 / 32
MASK_SUPERSAMPLING: Final[int] = 4
WINDOWS_ICON_SIZES: Final[tuple[tuple[int, int], ...]] = (
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
)


def windows_icon(target: Path) -> Path:
    """The app's icon as a Windows .ico, holding every size Explorer and the Start menu draw it at."""
    _desktop_icon().save(target, format="ICO", sizes=list(WINDOWS_ICON_SIZES))
    return target


def macos_icon(target: Path) -> Path:
    """The app's icon as a macOS .icns, its sizes scaled from the 512-pixel source."""
    _desktop_icon().save(target, format="ICNS")
    return target


def linux_icon(target: Path) -> Path:
    _desktop_icon().save(target, format="PNG")
    return target


def _desktop_icon() -> Image.Image:
    """The web app's icon with its corners transparent, as desktops draw an icon.

    The web icon fills its square, the corners outside its rounded square painted in the page's
    color; the rounded square's radius comes from `favicon.svg`, and the mask is drawn at a larger
    size and scaled down for smooth edges.
    """
    with Image.open(APP_ICON) as image:
        icon = image.convert("RGBA")
    mask_size = icon.width * MASK_SUPERSAMPLING
    mask = Image.new("L", (mask_size, mask_size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, mask_size - 1, mask_size - 1), radius=round(mask_size * CORNER_RADIUS_FRACTION), fill=255
    )
    icon.putalpha(mask.resize(icon.size, Image.Resampling.LANCZOS))
    return icon
