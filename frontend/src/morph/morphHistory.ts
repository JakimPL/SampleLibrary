import type { MorphEnd, MorphPair } from "./morphStore";

/** How many distinct samples each end's column keeps. */
export const HELD_CAPACITY = 50;
/** How many snapshots stand behind the present for undo. */
export const UNDO_DEPTH = 100;

export const MORPH_ENDS: readonly MorphEnd[] = ["first", "second"];

/** The samples each end has held, newest arrival first, each once per column. */
export type Held = Readonly<Record<MorphEnd, readonly string[]>>;

/** Everything one change to the ends moves, and undo brings back: the ends, the point drawn, and the slider's weight. */
export interface MorphSnapshot extends MorphPair {
    readonly weight: number;
}

export interface MorphHistory {
    readonly held: Held;
    /** The snapshots behind the present, oldest first; the last is what undo restores. */
    readonly past: readonly MorphSnapshot[];
    /** The snapshots undone, the last being what redo restores. */
    readonly future: readonly MorphSnapshot[];
}

/** A history moved one step along its line, and the snapshot that step makes current. */
export interface Restored {
    readonly history: MorphHistory;
    readonly snapshot: MorphSnapshot;
}

export const EMPTY_HELD: Held = { first: [], second: [] };
export const EMPTY_HISTORY: MorphHistory = { held: EMPTY_HELD, past: [], future: [] };

/** The four fields a snapshot holds, read off any state that carries them. */
export function snapshotOf(state: MorphSnapshot): MorphSnapshot {
    return { first: state.first, second: state.second, renderedWeight: state.renderedWeight, weight: state.weight };
}

export function sameSnapshot(one: MorphSnapshot, other: MorphSnapshot): boolean {
    return (
        one.first === other.first &&
        one.second === other.second &&
        one.renderedWeight === other.renderedWeight &&
        one.weight === other.weight
    );
}

/** The column with `hash` at its top when it was absent, held to the capacity from the tail; the column itself otherwise. */
function withArrival(column: readonly string[], hash: string | null): readonly string[] {
    if (hash === null || column.includes(hash)) {
        return column;
    }
    return [hash, ...column].slice(0, HELD_CAPACITY);
}

/**
 * The columns with each end's sample in them: a sample an end holds for the first time goes on
 * top of that end's column, and a sample the column already knows leaves it as it is, so a row
 * keeps its place for as long as it stays. Columns that gain nothing come back as the same value.
 */
export function remembering(held: Held, pair: MorphPair): Held {
    const first = withArrival(held.first, pair.first);
    const second = withArrival(held.second, pair.second);
    return first === held.first && second === held.second ? held : { first, second };
}

/**
 * The history after a change from `prior` to `next`: `prior` joins the line behind the present,
 * the oldest snapshot leaving once the line is full, the changes undone before are let go, and
 * the columns remember `next`.
 */
export function recorded(history: MorphHistory, prior: MorphSnapshot, next: MorphPair): MorphHistory {
    return {
        held: remembering(history.held, next),
        past: [...history.past, prior].slice(-UNDO_DEPTH),
        future: [],
    };
}

/** One step back along the line: the last snapshot behind `current` becomes current, and `current` waits ahead for redo. */
export function undone(history: MorphHistory, current: MorphSnapshot): Restored | null {
    const snapshot = history.past.at(-1);
    if (snapshot === undefined) {
        return null;
    }
    return {
        history: {
            held: remembering(history.held, snapshot),
            past: history.past.slice(0, -1),
            future: [...history.future, current],
        },
        snapshot,
    };
}

/** One step forward along the line: the snapshot last undone becomes current again, and `current` goes back behind it. */
export function redone(history: MorphHistory, current: MorphSnapshot): Restored | null {
    const snapshot = history.future.at(-1);
    if (snapshot === undefined) {
        return null;
    }
    return {
        history: {
            held: remembering(history.held, snapshot),
            past: [...history.past, current],
            future: history.future.slice(0, -1),
        },
        snapshot,
    };
}

/** The columns emptied, keeping the samples the ends hold now as their only rows. */
export function forgotten(pair: MorphPair): Held {
    return remembering(EMPTY_HELD, pair);
}

/** Whether `hash` is the sample `end` holds right now, which marks its row in the column. */
export function isHeld(pair: MorphPair, end: MorphEnd, hash: string): boolean {
    return pair[end] === hash;
}
