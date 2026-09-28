import { EMPTY_HELD, type Held, HELD_CAPACITY } from "./morphHistory";

export const MORPH_HISTORY_STORAGE_KEY = "sampleripper-morph-history";
const SAMPLE_HASH_PATTERN = /^[0-9a-f]{64}$/;

function isColumn(value: unknown): value is readonly string[] {
    return (
        Array.isArray(value) &&
        value.every((hash) => typeof hash === "string" && SAMPLE_HASH_PATTERN.test(hash)) &&
        new Set(value).size === value.length
    );
}

/** Whether `value` is a saved record of both ends' columns: an array of distinct sample hashes for each. */
export function isHeldRecord(value: unknown): value is Held {
    if (typeof value !== "object" || value === null) {
        return false;
    }
    const record = value as Record<string, unknown>;
    return isColumn(record.first) && isColumn(record.second);
}

/** The columns an earlier visit saved, each held to the capacity, or empty columns for nothing saved or a record of another shape. */
export function readSavedHeld(): Held {
    try {
        const raw = localStorage.getItem(MORPH_HISTORY_STORAGE_KEY);
        if (raw === null) {
            return EMPTY_HELD;
        }
        const parsed: unknown = JSON.parse(raw);
        if (!isHeldRecord(parsed)) {
            return EMPTY_HELD;
        }
        return { first: parsed.first.slice(0, HELD_CAPACITY), second: parsed.second.slice(0, HELD_CAPACITY) };
    } catch {
        return EMPTY_HELD;
    }
}

export function saveHeld(held: Held): void {
    try {
        localStorage.setItem(MORPH_HISTORY_STORAGE_KEY, JSON.stringify(held));
    } catch {
        // localStorage throws in private browsing or on a full quota; the columns then last for this visit.
    }
}
