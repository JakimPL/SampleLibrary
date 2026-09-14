import { CATEGORY_ORDER, categoryIndex, type SampleCategory } from "../samples/category";
import { labelColor } from "../theme/labelPalette";
import type { CloudColors } from "./cloudRenderSettings";
import type { CloudEntityPoint } from "./geometry";
import { type PointColoring, SUBSTRATE_SLOT } from "./labelColoring";

const UNCATEGORIZED_CATEGORY: SampleCategory = "uncategorized";

/** Which palette slot each point of a categorized batch paints in. */
export interface PointSlots {
    /** Each point's slot, at the point's own index. */
    readonly slots: Uint16Array;
    /** The slot of the points that name nothing: the uncategorized ones, or those no painted tag reaches. */
    readonly substrateSlot: number;
    readonly slotCount: number;
}

/**
 * Each point's palette slot, or null for a batch where some point carries no category: a sample
 * cloud point always carries one ("uncategorized" at worst), a module cloud point never does, so a
 * null answer is the module cloud, drawn in one flat color. Under the category coloring a point's
 * slot is its category's place in `CATEGORY_ORDER`; under a label coloring it is the slot its first
 * painted tag holds.
 */
export function slotPoints(points: readonly CloudEntityPoint[], coloring: PointColoring): PointSlots | null {
    const categorized = points.length > 0 && points.every((point) => point.category !== undefined);
    if (!categorized) {
        return null;
    }
    const slots = new Uint16Array(points.length);
    if (coloring.kind === "label") {
        points.forEach((point, index) => {
            slots[index] = coloring.slotByHash.get(point.ref.hash) ?? SUBSTRATE_SLOT;
        });
        return { slots, substrateSlot: SUBSTRATE_SLOT, slotCount: coloring.ranks.length + 1 };
    }
    points.forEach((point, index) => {
        slots[index] = categoryIndex(point.category ?? UNCATEGORIZED_CATEGORY);
    });
    return { slots, substrateSlot: categoryIndex(UNCATEGORIZED_CATEGORY), slotCount: CATEGORY_ORDER.length };
}

/** One color per slot `slotPoints` hands out under `coloring`, the substrate's in the recessive tone. */
export function paletteColors(coloring: PointColoring, colors: CloudColors): readonly string[] {
    if (coloring.kind === "label") {
        return [colors.uncategorized, ...coloring.ranks.map((rank) => labelColor(rank, colors.labels))];
    }
    return colors.categories;
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
 * the categories among them interleave.
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
