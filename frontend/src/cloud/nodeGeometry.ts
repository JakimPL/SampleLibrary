import { parseCssColor } from "../theme/cssColor";
import type { CloudEntityPoint } from "./geometry";
import { drawOrder, type PointSlots } from "./pointPalette";

/** The node layer's vertex data: every point's position and palette slot, laid out in the order to draw them. */
export interface NodeGeometry {
    /** x and y of each node, in the normalized data space. */
    readonly positions: Float32Array;
    readonly slots: Float32Array;
    readonly count: number;
}

const COORDINATES_PER_POINT = 2;
const BYTES_PER_COLOR = 4;
const CHANNEL_MAXIMUM = 255;
const ALPHA_CHANNEL = 3;
const TRANSPARENT = [0, 0, 0, 0] as const;

/**
 * The nodes of `points` in drawing order: under a categorized batch the substrate's points first,
 * as the scatterplot draws them, so the named points' markers sit on top; a batch of one flat
 * color keeps its own order in slot zero.
 */
export function nodeGeometryOf(points: readonly CloudEntityPoint[], slotting: PointSlots | null): NodeGeometry {
    const order = slotting === null ? null : drawOrder(slotting);
    const positions = new Float32Array(points.length * COORDINATES_PER_POINT);
    const slots = new Float32Array(points.length);
    for (let rank = 0; rank < points.length; rank += 1) {
        const index = order?.[rank] ?? rank;
        const point = points[index];
        positions[rank * COORDINATES_PER_POINT] = point?.x ?? 0;
        positions[rank * COORDINATES_PER_POINT + 1] = point?.y ?? 0;
        slots[rank] = slotting?.slots[index] ?? 0;
    }
    return { positions, slots, count: points.length };
}

/**
 * One RGBA byte quadruple per palette slot, the substrate's slot scaled to `substrateOpacity`; a
 * color the stylesheet writes in some form other than hex or `rgb()` paints its slot transparent.
 */
export function nodePaletteOf(
    colors: readonly string[],
    substrateSlot: number | null,
    substrateOpacity: number,
): Uint8Array {
    const bytes = new Uint8Array(Math.max(1, colors.length) * BYTES_PER_COLOR);
    colors.forEach((color, slot) => {
        const channels = parseCssColor(color) ?? TRANSPARENT;
        const opacity = slot === substrateSlot ? substrateOpacity : 1;
        channels.forEach((channel, channelIndex) => {
            const scaled = channelIndex === ALPHA_CHANNEL ? channel * opacity : channel;
            bytes[slot * BYTES_PER_COLOR + channelIndex] = Math.round(scaled * CHANNEL_MAXIMUM);
        });
    });
    return bytes;
}
