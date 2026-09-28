import { describe, expect, it } from "vitest";

import {
    EMPTY_HELD,
    EMPTY_HISTORY,
    forgotten,
    type Held,
    HELD_CAPACITY,
    isHeld,
    type MorphHistory,
    type MorphSnapshot,
    recorded,
    redone,
    remembering,
    sameSnapshot,
    snapshotOf,
    UNDO_DEPTH,
    undone,
} from "../../src/morph/morphHistory";
import type { MorphPair } from "../../src/morph/morphStore";

const A = "a".repeat(64);
const B = "b".repeat(64);
const C = "c".repeat(64);
const D = "d".repeat(64);

function pair(first: string | null, second: string | null): MorphPair {
    return { first, second, renderedWeight: null };
}

function snapshot(first: string | null, second: string | null, weight = 0.5): MorphSnapshot {
    return { first, second, renderedWeight: first !== null && second !== null ? weight : null, weight };
}

/** `count` distinct sample hashes. */
function hashes(count: number): readonly string[] {
    return Array.from({ length: count }, (_, index) => index.toString(16).padStart(64, "0"));
}

describe("snapshotOf", () => {
    it("reads the four fields a change moves off a wider state", () => {
        const state = { ...snapshot(A, B, 0.25), selectedEnd: "first", held: EMPTY_HELD };

        expect(snapshotOf(state)).toEqual({ first: A, second: B, renderedWeight: 0.25, weight: 0.25 });
    });
});

describe("sameSnapshot", () => {
    it("tells two snapshots apart by any of the four fields", () => {
        expect(sameSnapshot(snapshot(A, B), snapshot(A, B))).toBe(true);
        expect(sameSnapshot(snapshot(A, B), snapshot(A, C))).toBe(false);
        expect(sameSnapshot(snapshot(A, B), snapshot(C, B))).toBe(false);
        expect(sameSnapshot(snapshot(A, B, 0.5), snapshot(A, B, 0.75))).toBe(false);
        expect(sameSnapshot({ ...snapshot(A, B), renderedWeight: 0.1 }, snapshot(A, B))).toBe(false);
    });
});

describe("remembering", () => {
    /** One pair remembered by the columns: what they held, and what they hold after, or `null` for the same columns. */
    interface RememberCase {
        readonly name: string;
        readonly held: Held;
        readonly pair: MorphPair;
        readonly expected: Held | null;
    }

    const REMEMBER_CASES: readonly RememberCase[] = [
        {
            name: "puts a sample an end holds for the first time on top of its column",
            held: { first: [A], second: [] },
            pair: pair(C, null),
            expected: { first: [C, A], second: [] },
        },
        {
            name: "leaves the columns as they are while the ends hold nothing new",
            held: { first: [A], second: [B] },
            pair: pair(A, null),
            expected: null,
        },
        {
            name: "leaves a column that already knows the sample, wherever it stands",
            held: { first: [C, A], second: [B] },
            pair: pair(A, B),
            expected: null,
        },
        {
            name: "remembers both ends at once",
            held: EMPTY_HELD,
            pair: pair(A, B),
            expected: { first: [A], second: [B] },
        },
        {
            name: "keeps each column its own, a sample the other end held arriving afresh",
            held: { first: [A], second: [] },
            pair: pair(B, A),
            expected: { first: [B, A], second: [A] },
        },
    ];

    it.each(REMEMBER_CASES)("$name", ({ held, pair: remembered, expected }: RememberCase) => {
        const result = remembering(held, remembered);

        if (expected === null) {
            expect(result).toBe(held);
        } else {
            expect(result).toEqual(expected);
        }
    });

    it("holds a column to its capacity, the oldest sample leaving", () => {
        const column = hashes(HELD_CAPACITY);

        const result = remembering({ first: column, second: [] }, pair(A, null));

        expect(result.first).toHaveLength(HELD_CAPACITY);
        expect(result.first[0]).toBe(A);
        expect(result.first.slice(1)).toEqual(column.slice(0, -1));
        expect(result.first).not.toContain(column.at(-1));
    });
});

describe("recorded", () => {
    it("puts the prior snapshot behind the present, lets the future go, and remembers the next pair", () => {
        const history: MorphHistory = {
            held: { first: [A], second: [] },
            past: [snapshot(null, null)],
            future: [snapshot(C, D)],
        };

        const result = recorded(history, snapshot(A, null), pair(A, B));

        expect(result.past).toEqual([snapshot(null, null), snapshot(A, null)]);
        expect(result.future).toEqual([]);
        expect(result.held).toEqual({ first: [A], second: [B] });
    });

    it("holds the line to its depth, the oldest snapshot leaving", () => {
        const past = Array.from({ length: UNDO_DEPTH }, (_, index) => snapshot(A, B, index / UNDO_DEPTH));
        const prior = snapshot(A, C);

        const result = recorded({ ...EMPTY_HISTORY, past }, prior, pair(A, D));

        expect(result.past).toHaveLength(UNDO_DEPTH);
        expect(result.past[0]).toEqual(past[1]);
        expect(result.past.at(-1)).toEqual(prior);
    });
});

describe("undone and redone", () => {
    const current = snapshot(A, C, 0.75);
    const behind = snapshot(A, B, 0.25);
    const history: MorphHistory = {
        held: { first: [A], second: [C, B] },
        past: [snapshot(A, null), behind],
        future: [],
    };

    it("answers nothing with no step to take", () => {
        expect(undone(EMPTY_HISTORY, current)).toBeNull();
        expect(redone(EMPTY_HISTORY, current)).toBeNull();
    });

    it("steps back to the last snapshot, the current one waiting ahead", () => {
        const restored = undone(history, current);

        expect(restored?.snapshot).toEqual(behind);
        expect(restored?.history.past).toEqual([snapshot(A, null)]);
        expect(restored?.history.future).toEqual([current]);
    });

    it("comes back to where it started after a step back and a step forward", () => {
        const back = undone(history, current);
        const forward = back === null ? null : redone(back.history, back.snapshot);

        expect(forward?.snapshot).toEqual(current);
        expect(forward?.history).toEqual(history);
    });

    it("remembers the ends a step restores, so their rows are there to mark", () => {
        const restored = undone({ ...EMPTY_HISTORY, past: [behind] }, current);

        expect(restored?.history.held).toEqual({ first: [A], second: [B] });
    });
});

describe("forgotten", () => {
    it("keeps the samples the ends hold now as the only rows", () => {
        expect(forgotten(pair(A, B))).toEqual({ first: [A], second: [B] });
        expect(forgotten(pair(null, B))).toEqual({ first: [], second: [B] });
    });

    it("empties both columns outright while the ends hold nothing", () => {
        expect(forgotten(pair(null, null))).toBe(EMPTY_HELD);
    });
});

describe("isHeld", () => {
    it("marks the sample an end holds right now and no other", () => {
        expect(isHeld(pair(A, B), "first", A)).toBe(true);
        expect(isHeld(pair(A, B), "second", A)).toBe(false);
        expect(isHeld(pair(null, B), "first", A)).toBe(false);
    });
});
