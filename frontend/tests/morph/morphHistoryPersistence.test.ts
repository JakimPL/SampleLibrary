import { beforeEach, describe, expect, it } from "vitest";

import { EMPTY_HELD, HELD_CAPACITY } from "../../src/morph/morphHistory";
import {
    isHeldRecord,
    MORPH_HISTORY_STORAGE_KEY,
    readSavedHeld,
    saveHeld,
} from "../../src/morph/morphHistoryPersistence";

const A = "a".repeat(64);
const B = "b".repeat(64);

/** `count` distinct sample hashes. */
function hashes(count: number): readonly string[] {
    return Array.from({ length: count }, (_, index) => index.toString(16).padStart(64, "0"));
}

describe("readSavedHeld", () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it("reads empty columns while nothing was saved", () => {
        expect(readSavedHeld()).toEqual(EMPTY_HELD);
    });

    it("reads back the columns that were saved", () => {
        saveHeld({ first: [A, B], second: [B] });

        expect(readSavedHeld()).toEqual({ first: [A, B], second: [B] });
        expect(localStorage.getItem(MORPH_HISTORY_STORAGE_KEY)).toBe(JSON.stringify({ first: [A, B], second: [B] }));
    });

    /** One record of another shape, read as empty columns. */
    interface BadRecordCase {
        readonly name: string;
        readonly raw: string;
    }

    const BAD_RECORDS: readonly BadRecordCase[] = [
        { name: "a record that is not JSON", raw: "{" },
        { name: "an array in place of the record", raw: "[]" },
        { name: "a record missing a column", raw: JSON.stringify({ first: [A] }) },
        { name: "a hash too short to be one", raw: JSON.stringify({ first: ["abc"], second: [] }) },
        { name: "a hash repeated within a column", raw: JSON.stringify({ first: [A, A], second: [] }) },
        { name: "a number in a column", raw: JSON.stringify({ first: [1], second: [] }) },
    ];

    it.each(BAD_RECORDS)("reads empty columns from $name", ({ raw }: BadRecordCase) => {
        localStorage.setItem(MORPH_HISTORY_STORAGE_KEY, raw);

        expect(readSavedHeld()).toEqual(EMPTY_HELD);
    });

    it("holds each saved column to the capacity, the newest kept", () => {
        const column = hashes(HELD_CAPACITY + 5);
        localStorage.setItem(MORPH_HISTORY_STORAGE_KEY, JSON.stringify({ first: column, second: [] }));

        expect(readSavedHeld().first).toEqual(column.slice(0, HELD_CAPACITY));
    });
});

describe("isHeldRecord", () => {
    it("knows a record of two columns of distinct hashes", () => {
        expect(isHeldRecord({ first: [A], second: [] })).toBe(true);
        expect(isHeldRecord({ first: [A], second: [A] })).toBe(true);
        expect(isHeldRecord({ first: [], second: [B, A] })).toBe(true);
    });

    it("rejects anything else", () => {
        expect(isHeldRecord(null)).toBe(false);
        expect(isHeldRecord("held")).toBe(false);
        expect(isHeldRecord({ first: [A] })).toBe(false);
        expect(isHeldRecord({ first: [A], second: [A.toUpperCase()] })).toBe(false);
    });
});
