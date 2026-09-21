import { labelColor } from "../theme/labelPalette";
import type { CloudColors } from "./cloudRenderSettings";
import type { CloudEntityPoint } from "./geometry";
import { type PointColoring, SUBSTRATE_SLOT } from "./labelColoring";

/** Which palette slot each point of a sample batch paints in. */
export interface PointSlots {
    /** Each point's slot, at the point's own index. */
    readonly slots: Uint16Array;
    /** The slot of the points that name nothing: those no painted tag reaches. */
    readonly substrateSlot: number;
    readonly slotCount: number;
}

/**
 * Each point's palette slot, or null for the module cloud, drawn in one flat color. A sample point
 * takes the slot its first painted tag holds, and the substrate's slot where no painted tag reaches it.
 */
export function slotPoints(points: readonly CloudEntityPoint[], coloring: PointColoring): PointSlots | null {
    const samples = points.length > 0 && points.every((point) => point.ref.kind === "sample");
    if (!samples) {
        return null;
    }
    const slots = new Uint16Array(points.length);
    points.forEach((point, index) => {
        slots[index] = coloring.slotByHash.get(point.ref.hash) ?? SUBSTRATE_SLOT;
    });
    return { slots, substrateSlot: SUBSTRATE_SLOT, slotCount: coloring.ranks.length + 1 };
}

/** One color per slot `slotPoints` hands out under `coloring`, the substrate's in the recessive tone. */
export function paletteColors(coloring: PointColoring, colors: CloudColors): readonly string[] {
    return [colors.uncategorized, ...coloring.ranks.map((rank) => labelColor(rank, colors.labels))];
}

/** One value per slot, such as an opacity or a size: the substrate's own, and the named points' for every other slot. */
export function slotValues(slotting: PointSlots, namedValue: number, substrateValue: number): number[] {
    return Array.from({ length: slotting.slotCount }, (_, slot) =>
        slot === slotting.substrateSlot ? substrateValue : namedValue,
    );
}

/**
 * Every point's index in the order to draw them: the substrate's points first, then the rest in
 * their own order, so the points that name something always draw above the ground they sit on and
 * the tags among them interleave.
 */
export function drawOrder(slotting: PointSlots): number[] {
    const order: number[] = [];
    slotting.slots.forEach((slot, index) => {
        if (slot === slotting.substrateSlot) {
            order.push(index);
        }
    });
    slotting.slots.forEach((slot, index) => {
        if (slot !== slotting.substrateSlot) {
            order.push(index);
        }
    });
    return order;
}
