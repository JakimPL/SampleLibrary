import type { PlanarPoint } from "./densifyCloud";

export interface SeedOptions<Item> {
    /** What makes one item's position its own: the same key always lands in the same place. */
    readonly keyOf: (item: Item) => string;
    /** Which cluster an item belongs to, so items of a kind land together. */
    readonly groupOf: (item: Item) => string;
}

const FNV_OFFSET_BASIS = 2166136261;
const FNV_PRIME = 16777619;
const UNSIGNED_32_BIT = 4294967296;
const GOLDEN_ANGLE_RADIANS = 2.399963229728653;
const FULL_TURN_RADIANS = 6.283185307179586;
const BOX_MULLER_SCALE = 2;
const GROUP_RING_RADIUS = 6;
const GROUP_RING_GROWTH = 0.35;
const GROUP_SPREAD = 1.1;
const MINIMUM_UNIFORM = 1e-9;
const HORIZONTAL_SALT = 1;
const VERTICAL_SALT = 2;

/**
 * A uniform value in [0, 1) read from a key through FNV-1a, salted so one key yields independent
 * values. A sample's hash is already uniform hex, so its digest places the point as evenly as a
 * random draw while landing it in the same place on every call.
 */
function digestOf(key: string, salt: number): number {
    let digest = FNV_OFFSET_BASIS ^ salt;
    for (let index = 0; index < key.length; index += 1) {
        digest ^= key.charCodeAt(index);
        digest = Math.imul(digest, FNV_PRIME);
    }
    return (digest >>> 0) / UNSIGNED_32_BIT;
}

/** A Gaussian pair from two uniform values, so a cluster thins toward its edge the way a real one does. */
function gaussianPair(first: number, second: number): readonly [number, number] {
    const magnitude = Math.sqrt(-BOX_MULLER_SCALE * Math.log(Math.max(first, MINIMUM_UNIFORM)));
    const angle = FULL_TURN_RADIANS * second;
    return [magnitude * Math.cos(angle), magnitude * Math.sin(angle)];
}

/** One center per group on a golden-angle spiral, each further out than the last, which keeps any number of groups apart. */
function groupCenters(groups: readonly string[]): Map<string, readonly [number, number]> {
    return new Map(
        groups.map((group, index) => {
            const angle = index * GOLDEN_ANGLE_RADIANS;
            const radius = GROUP_RING_RADIUS * (1 + index * GROUP_RING_GROWTH);
            return [group, [radius * Math.cos(angle), radius * Math.sin(angle)] as const];
        }),
    );
}

/**
 * Lays a set of items out as a plane of clusters, one cluster per group, so a sandbox that has yet
 * to run an embedding still shows a cloud with structure to look at. A key always lands in the same
 * place whatever order the items arrive in.
 */
export function seedLayout<Item>(items: readonly Item[], options: SeedOptions<Item>): readonly (Item & PlanarPoint)[] {
    const groups = [...new Set(items.map(options.groupOf))].sort();
    const centers = groupCenters(groups);
    return items.map((item) => {
        const key = options.keyOf(item);
        const center = centers.get(options.groupOf(item)) ?? [0, 0];
        const [offsetX, offsetY] = gaussianPair(digestOf(key, HORIZONTAL_SALT), digestOf(key, VERTICAL_SALT));
        return {
            ...item,
            x: center[0] + GROUP_SPREAD * offsetX,
            y: center[1] + GROUP_SPREAD * offsetY,
        };
    });
}
