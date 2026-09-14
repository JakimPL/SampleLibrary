import { accumulateDensity, blurDensity, glowPixels } from "./densityField";
import type { DeviceSize } from "./gridPainter";
import type { NodeGeometry } from "./nodeGeometry";
import { type DataBounds, toScreen, type ViewTransform } from "./viewTransform";

/** A density glow ready to paint: the image, and the data-space box it covers. */
export interface GlowImage {
    readonly image: HTMLCanvasElement;
    readonly domain: DataBounds;
}

/** The part of a 2D canvas context a glow paints through. */
export interface GlowCanvas {
    imageSmoothingEnabled: boolean;
    drawImage: (image: HTMLCanvasElement, x: number, y: number, width: number, height: number) => void;
}

const GLOW_RESOLUTION = 256;
const GLOW_BLUR_RADIUS = 4;
const GLOW_BLUR_PASSES = 3;
const GLOW_DOMAIN: DataBounds = { minimumX: -1.25, maximumX: 1.25, minimumY: -1.25, maximumY: 1.25 };

/**
 * The glow of the density of `geometry`'s named points, tinted cell by cell with the average
 * `palette` color of the points beneath it, so each classified cluster gathers a haze of its own hue.
 * The substrate's points, in `substrateSlot`, stay out: the substrate's own dots already show its
 * density, and leaving it out keeps the named clusters' glow from being measured against it. The
 * glow covers the normalized data space with a margin to fade out in, at a resolution the camera
 * stretches smoothly when zoomed in. Null when the theme turns the glow off (`opacity` zero), the
 * batch holds no points, or the document yields no 2D canvas to draw it on.
 */
export function glowImageOf(
    geometry: NodeGeometry,
    palette: Uint8Array,
    substrateSlot: number | null,
    opacity: number,
): GlowImage | null {
    if (opacity <= 0 || geometry.count === 0) {
        return null;
    }
    const image = document.createElement("canvas");
    image.width = GLOW_RESOLUTION;
    image.height = GLOW_RESOLUTION;
    const context = image.getContext("2d");
    if (context === null) {
        return null;
    }
    const field = blurDensity(
        accumulateDensity(geometry, palette, GLOW_RESOLUTION, GLOW_DOMAIN, substrateSlot),
        GLOW_BLUR_RADIUS,
        GLOW_BLUR_PASSES,
    );
    const pixels = context.createImageData(GLOW_RESOLUTION, GLOW_RESOLUTION);
    pixels.data.set(glowPixels(field, opacity));
    context.putImageData(pixels, 0, 0);
    return { image, domain: GLOW_DOMAIN };
}

/** Paints `glow` onto a canvas of `size` device pixels, stretched over the part of the screen its data-space box covers. */
export function paintGlow(context: GlowCanvas, transform: ViewTransform, glow: GlowImage, size: DeviceSize): void {
    const [left, top] = toScreen(transform, glow.domain.minimumX, glow.domain.maximumY);
    const [right, bottom] = toScreen(transform, glow.domain.maximumX, glow.domain.minimumY);
    const scaleX = size.width / transform.widthPx;
    const scaleY = size.height / transform.heightPx;
    context.imageSmoothingEnabled = true;
    context.drawImage(glow.image, left * scaleX, top * scaleY, (right - left) * scaleX, (bottom - top) * scaleY);
}
