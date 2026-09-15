import { describe, expect, it } from "vitest";

import type { CloudLabel } from "../../src/api/cloud";
import type { TagSummary } from "../../src/api/curation";
import {
    DEFAULT_PAINTED_TAG_COUNT,
    defaultPaintedTags,
    labelColoring,
    labelSlots,
    SUBSTRATE_SLOT,
    topLevelTags,
} from "../../src/cloud/labelColoring";

const TAGS: readonly TagSummary[] = [
    { path: ["LO-FI"], sample_count: 3, rank: 2 },
    { path: ["HI-HAT"], sample_count: 2, rank: 0 },
    { path: ["HI-HAT", "CLOSED"], sample_count: 2, rank: 1 },
    { path: ["SNARE"], sample_count: 2, rank: 3 },
];

const LABELS: readonly CloudLabel[] = [
    { sample_hash: "a".repeat(64), paths: [["HI-HAT", "CLOSED"], ["LO-FI"]] },
    { sample_hash: "b".repeat(64), paths: [["LO-FI"], ["SNARE"]] },
    { sample_hash: "c".repeat(64), paths: [["SNARE"]] },
];

describe("topLevelTags", () => {
    it("keeps the broad categories, most used first and ties by name", () => {
        expect(topLevelTags(TAGS).map((tag) => tag.name)).toEqual(["LO-FI", "HI-HAT", "SNARE"]);
    });
});

describe("defaultPaintedTags", () => {
    it("paints the most used tags, up to the count that stays tellable apart", () => {
        const many = Array.from({ length: DEFAULT_PAINTED_TAG_COUNT + 3 }, (_, index) => ({
            name: `TAG ${String(index)}`,
            sampleCount: 100 - index,
            rank: index,
        }));

        expect(defaultPaintedTags(many)).toHaveLength(DEFAULT_PAINTED_TAG_COUNT);
        expect(defaultPaintedTags(many)[0]).toBe("TAG 0");
    });
});

describe("labelSlots", () => {
    it("paints a sample by the first tag it was given that is painted", () => {
        const slots = labelSlots(LABELS, ["SNARE", "LO-FI"]);

        expect(slots.get("a".repeat(64))).toBe(2);
        expect(slots.get("b".repeat(64))).toBe(2);
        expect(slots.get("c".repeat(64))).toBe(1);
    });

    it("leaves a sample on the substrate when none of its tags is painted", () => {
        const slots = labelSlots(LABELS, ["HI-HAT"]);

        expect(slots.get("a".repeat(64))).toBe(1);
        expect(slots.has("b".repeat(64))).toBe(false);
        expect(slots.get("b".repeat(64)) ?? SUBSTRATE_SLOT).toBe(SUBSTRATE_SLOT);
    });
});

describe("labelColoring", () => {
    it("carries each painted tag's lasting rank in slot order and ignores a tag nobody used", () => {
        const coloring = labelColoring(LABELS, topLevelTags(TAGS), ["SNARE", "KICK", "HI-HAT"]);

        expect(coloring.ranks).toEqual([3, 0]);
        expect(coloring.slotByHash.get("a".repeat(64))).toBe(2);
        expect(coloring.slotByHash.get("c".repeat(64))).toBe(1);
    });
});
