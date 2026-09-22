import { useCloudDotsStore } from "./cloudDotsStore";
import type { NodeStyle, PointStyle } from "./cloudRenderSettings";
import { floatRenderingSupport, needsPlainDots } from "./floatRendering";

/** Why the points draw as plain dots: a person chose so, or the browser's WebGL blends no float buffers. */
export type PlainDotsReason = "chosen" | "unsupported";

const SMALLEST_DOT_PX = 2;

/** The reason the node layer draws the points in the scatterplot's place, or `null` while the scatterplot draws them. */
export function usePlainDots(): PlainDotsReason | null {
    const dots = useCloudDotsStore((state) => state.dots);
    if (dots === "plain") {
        return "chosen";
    }
    return needsPlainDots(floatRenderingSupport()) ? "unsupported" : null;
}

/** The node layer's style when it stands in for the scatterplot: every point a filled dot the size the theme draws its points, the substrate as faint; the frame style adds the growth. */
export function plainDotStyle(point: PointStyle): NodeStyle {
    return {
        mode: "always",
        sizePx: Math.max(SMALLEST_DOT_PX, Math.round(point.sizePx)),
        lineWidthPx: 0,
        fillOpacity: 1,
        substrateOpacity: point.substrateOpacity,
    };
}
