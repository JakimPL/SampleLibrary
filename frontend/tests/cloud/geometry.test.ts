import { describe, expect, it } from "vitest";

import type { CloudEntityPoint } from "../../src/cloud/geometry";
import { normalizePoints } from "../../src/cloud/geometry";
import type { EntityRef } from "../../src/workspace/selectionStore";

function point(ref: EntityRef, x: number, y: number): CloudEntityPoint {
    return { ref, x, y };
}

const sampleA: EntityRef = { kind: "sample", hash: "a".repeat(64) };
const sampleB: EntityRef = { kind: "sample", hash: "b".repeat(64) };

describe("normalizePoints", () => {
    it("returns nothing for an empty input", () => {
        expect(normalizePoints([])).toEqual([]);
    });

    it("maps the bounding box of the input onto [-1, 1]", () => {
        const points = [point(sampleA, 0, 0), point(sampleB, 10, 20)];

        const normalized = normalizePoints(points);

        expect(normalized).toEqual([
            { ref: sampleA, x: -1, y: -1 },
            { ref: sampleB, x: 1, y: 1 },
        ]);
    });

    it("does not divide by zero when every point shares a coordinate", () => {
        const points = [point(sampleA, 5, 5), point(sampleB, 5, 5)];

        const normalized = normalizePoints(points);

        expect(normalized.every((entry) => Number.isFinite(entry.x) && Number.isFinite(entry.y))).toBe(true);
    });
});
