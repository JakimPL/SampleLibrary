import { describe, expect, it } from "vitest";

import { seedLayout } from "../../dev/cloudSeed";

interface Row {
    readonly hash: string;
    readonly category: string;
}

const ROWS: readonly Row[] = [
    { hash: "a".repeat(64), category: "kick" },
    { hash: "b".repeat(64), category: "kick" },
    { hash: "c".repeat(64), category: "snare" },
    { hash: "d".repeat(64), category: "uncategorized" },
];

const options = { keyOf: (row: Row) => row.hash, groupOf: (row: Row) => row.category };

function centerOf(rows: readonly (Row & { x: number; y: number })[], category: string): readonly [number, number] {
    const group = rows.filter((row) => row.category === category);
    return [
        group.reduce((sum, row) => sum + row.x, 0) / group.length,
        group.reduce((sum, row) => sum + row.y, 0) / group.length,
    ];
}

describe("seedLayout", () => {
    it("places every item once, keeping what it already carried", () => {
        const placed = seedLayout(ROWS, options);

        expect(placed).toHaveLength(ROWS.length);
        expect(placed.map((row) => row.hash)).toEqual(ROWS.map((row) => row.hash));
        expect(placed.map((row) => row.category)).toEqual(ROWS.map((row) => row.category));
    });

    it("gives every item a finite position", () => {
        for (const row of seedLayout(ROWS, options)) {
            expect(Number.isFinite(row.x)).toBe(true);
            expect(Number.isFinite(row.y)).toBe(true);
        }
    });

    it("lands the same key in the same place on every call", () => {
        expect(seedLayout(ROWS, options)).toEqual(seedLayout(ROWS, options));
    });

    it("keeps a key's place regardless of the order the items arrive in", () => {
        const reversed = seedLayout([...ROWS].reverse(), options);
        const forward = seedLayout(ROWS, options);
        const first = forward[0];
        const same = reversed.find((row) => row.hash === first?.hash);

        expect(same?.x).toBe(first?.x);
        expect(same?.y).toBe(first?.y);
    });

    it("holds one group's items closer to their own center than to another group's", () => {
        const placed = seedLayout(ROWS, options);
        const kickCenter = centerOf(placed, "kick");
        const snareCenter = centerOf(placed, "snare");
        const kicks = placed.filter((row) => row.category === "kick");

        for (const kick of kicks) {
            const toOwn = Math.hypot(kick.x - kickCenter[0], kick.y - kickCenter[1]);
            const toOther = Math.hypot(kick.x - snareCenter[0], kick.y - snareCenter[1]);
            expect(toOwn).toBeLessThan(toOther);
        }
    });

    it("separates the groups it is given", () => {
        const placed = seedLayout(ROWS, options);
        const kickCenter = centerOf(placed, "kick");
        const snareCenter = centerOf(placed, "snare");

        expect(Math.hypot(kickCenter[0] - snareCenter[0], kickCenter[1] - snareCenter[1])).toBeGreaterThan(1);
    });

    it("answers an empty catalog with no points", () => {
        expect(seedLayout([], options)).toEqual([]);
    });
});
