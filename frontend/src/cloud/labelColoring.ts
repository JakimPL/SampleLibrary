import type { CloudLabel } from "../api/cloud";
import type { TagSummary } from "../api/curation";

/** How many of the most-used tags are painted before a person chooses their own. */
export const DEFAULT_PAINTED_TAG_COUNT = 8;
/** The palette slot every point takes that no painted tag reaches: the ground the painted ones sit on. */
export const SUBSTRATE_SLOT = 0;

/** A top-level tag as the legend lists it: its name, how many samples carry it, and its lasting rank. */
export interface TopLevelTag {
    readonly name: string;
    readonly sampleCount: number;
    readonly rank: number;
}

/** How the cloud's sample points are colored: by the keyword category, or by the painted tags. */
export type PointColoring =
    | { readonly kind: "category" }
    | {
          readonly kind: "label";
          /** The palette slot of every labeled sample that a painted tag reaches. */
          readonly slotByHash: ReadonlyMap<string, number>;
          /** The lasting rank of each painted tag, in slot order; slot `i + 1` paints in `ranks[i]`'s color. */
          readonly ranks: readonly number[];
      };

/** The broad categories alone, most used first, ties by name. */
export function topLevelTags(tags: readonly TagSummary[]): readonly TopLevelTag[] {
    return tags
        .flatMap((tag): TopLevelTag[] => {
            const [name] = tag.path;
            return tag.path.length === 1 && name !== undefined
                ? [{ name, sampleCount: tag.sample_count, rank: tag.rank }]
                : [];
        })
        .sort((first, second) => second.sampleCount - first.sampleCount || first.name.localeCompare(second.name));
}

/** The tags painted until a person picks their own: the most used, as many as stay tellable apart. */
export function defaultPaintedTags(tags: readonly TopLevelTag[]): readonly string[] {
    return tags.slice(0, DEFAULT_PAINTED_TAG_COUNT).map((tag) => tag.name);
}

/**
 * The palette slot each labeled sample paints in: `SUBSTRATE_SLOT` where none of its tags is painted,
 * otherwise one past the position of its first painted tag in `painted`.
 *
 * A point shows one color, and a sample carries several tags, so one has to decide: the first tag
 * the person wrote that is among the painted ones, since the order they wrote in is the one reading
 * of the label that says which tag they thought of first.
 */
export function labelSlots(labels: readonly CloudLabel[], painted: readonly string[]): ReadonlyMap<string, number> {
    const slotByTag = new Map(painted.map((name, index) => [name, index + 1]));
    const slotByHash = new Map<string, number>();
    for (const label of labels) {
        const slot = label.paths
            .map(([top]) => (top === undefined ? undefined : slotByTag.get(top)))
            .find((candidate) => candidate !== undefined);
        if (slot !== undefined) {
            slotByHash.set(label.sample_hash, slot);
        }
    }
    return slotByHash;
}

/** The coloring the painted tags describe, ready for the view to draw. */
export function labelColoring(
    labels: readonly CloudLabel[],
    tags: readonly TopLevelTag[],
    painted: readonly string[],
): PointColoring {
    const rankByName = new Map(tags.map((tag) => [tag.name, tag.rank]));
    const known = painted.flatMap((name) => {
        const rank = rankByName.get(name);
        return rank === undefined ? [] : [{ name, rank }];
    });
    return {
        kind: "label",
        slotByHash: labelSlots(
            labels,
            known.map((tag) => tag.name),
        ),
        ranks: known.map((tag) => tag.rank),
    };
}
