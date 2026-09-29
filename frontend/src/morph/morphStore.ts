import { create } from "zustand";

import {
    EMPTY_HISTORY,
    forgotten,
    type MorphHistory,
    type MorphSnapshot,
    recorded,
    redone,
    type Restored,
    sameSnapshot,
    snapshotOf,
    undone,
} from "./morphHistory";
import { readSavedHeld, saveHeld } from "./morphHistoryPersistence";

const WEIGHT_STEPS = 100;
export const WEIGHT_STEP = 1 / WEIGHT_STEPS;
export const DEFAULT_WEIGHT = 0.5;

/** Which end of the pair a control speaks of. */
export type MorphEnd = "first" | "second";

/** The letter each end goes by on screen. */
export const END_LETTERS: Readonly<Record<MorphEnd, string>> = { first: "A", second: "B" };

/**
 * The weight held to the unit interval and to the grid of hundredths the renderer serves, so a
 * snapped weight writes as one two-place decimal in a URL and names exactly one cached render.
 */
export function snapWeight(weight: number): number {
    const clamped = Math.min(1, Math.max(0, weight));
    return Math.round(clamped * WEIGHT_STEPS) / WEIGHT_STEPS;
}

export interface MorphPair {
    readonly first: string | null;
    readonly second: string | null;
    /**
     * The weight of the render on screen: the slider's point once both ends are chosen, then whichever
     * point was let go last; `null` while an end is missing.
     */
    readonly renderedWeight: number | null;
}

interface MorphState extends MorphSnapshot, MorphHistory {
    /** The end that takes every sample picked next. */
    readonly selectedEnd: MorphEnd;
}

interface MorphActions {
    /** Makes `hash` the sample at `end`; a sample already at the other end trades places with it, the weight mirrored. */
    readonly setEnd: (end: MorphEnd, hash: string) => void;
    readonly swap: () => void;
    readonly setWeight: (weight: number) => void;
    /** Records the current weight as the point whose render is on screen. */
    readonly markRendered: () => void;
    readonly selectEnd: (end: MorphEnd) => void;
    /**
     * Gives a picked sample to the selected end, and hands the selection to the other end while
     * that one is empty; a sample the pair already holds leaves everything as it is.
     */
    readonly takeSample: (hash: string) => void;
    /** Returns the ends, the drawn point and the slider to how they stood before the last change. */
    readonly undo: () => void;
    /** Brings the change last undone back. */
    readonly redo: () => void;
    /** Empties both columns of the history, keeping the samples the ends hold now as their only rows. */
    readonly forgetHeld: () => void;
}

export const INITIAL_MORPH_STATE: MorphState = {
    first: null,
    second: null,
    weight: DEFAULT_WEIGHT,
    renderedWeight: null,
    selectedEnd: "first",
    ...EMPTY_HISTORY,
};

const OTHER_END: Readonly<Record<MorphEnd, MorphEnd>> = { first: "second", second: "first" };

/**
 * The ends as chosen, at `weight`: a pair that stays keeps the render drawn for it, a pair just
 * completed is drawn at `weight` before any point of it is heard, and a pair missing an end has
 * nothing drawn.
 */
function pairOf(state: MorphSnapshot, first: string | null, second: string | null, weight: number): MorphSnapshot {
    if (first === state.first && second === state.second) {
        return { first, second, renderedWeight: state.renderedWeight, weight };
    }
    return { first, second, renderedWeight: first !== null && second !== null ? weight : null, weight };
}

/** The sample at the end opposite `end`. */
function otherEndOf(state: MorphPair, end: MorphEnd): string | null {
    return state[OTHER_END[end]];
}

/** The pair with `hash` at `end` and the other end as it stands. */
function withSampleAt(state: MorphSnapshot, end: MorphEnd, hash: string): MorphSnapshot {
    return end === "first"
        ? pairOf(state, hash, state.second, state.weight)
        : pairOf(state, state.first, hash, state.weight);
}

/** The ends traded, with the weight mirrored so the audible point stays where it was. */
function swappedOf(state: MorphSnapshot): MorphSnapshot {
    return pairOf(state, state.second, state.first, snapWeight(1 - state.weight));
}

/**
 * The pair a morph runs between, how far along it the listener stands, which point of the path is
 * drawn on screen, and which end is selected to take the next sample. The strip under the cloud
 * and the marker on the cloud share it, so the two are one control. The pair is its own state,
 * filled by the samples a person picks, so it stays where it was put while the shell's highlight
 * and focus move on.
 *
 * One end is always selected, the first one at the start of a visit, and it takes every sample
 * picked in a list or on the cloud through `takeSample`. Picking fills an empty pair in order:
 * once the selected end takes a sample while the other end is empty, the selection moves there,
 * so the first two picks make a pair; after that the selection stays where a slot's tap put it.
 * Taking a sample the pair already holds keeps the pair and the selection as they stand, so a
 * double click's second click, or a tap to hear an end again, holds the pair in place. `setEnd`
 * names one end outright, which is how a row of the history gives its sample back, trading places
 * when the sample sits at the other end. `swap` mirrors the weight along with the ends, so the
 * audible point stays where it was, and keeps the selected letter. A render belongs to the pair it
 * was drawn for, so any change of the ends drops it.
 *
 * Every change to the ends passes through one `commit`, which keeps two records. The columns
 * (`held`) hold the samples each end has held, newest arrival first and each once, kept across
 * visits, so a row stays where it first appeared and the pair marks its rows by holding their
 * samples. The line (`past`, `future`) holds the snapshots behind the present, which `undo`
 * restores one by one and `redo` brings back until the next change; a snapshot carries the
 * weight and the drawn point along with the ends, so undoing a swap un-mirrors the slider and
 * the render comes back as it was.
 */
export const useMorphStore = create<MorphState & MorphActions>((set, get) => {
    function commit(next: MorphSnapshot): void {
        const state = get();
        const prior = snapshotOf(state);
        if (sameSnapshot(prior, next)) {
            return;
        }
        const history = recorded(state, prior, next);
        if (history.held !== state.held) {
            saveHeld(history.held);
        }
        set({ ...next, ...history });
    }

    function restore(restored: Restored | null): void {
        if (restored === null) {
            return;
        }
        if (restored.history.held !== get().held) {
            saveHeld(restored.history.held);
        }
        set({ ...restored.snapshot, ...restored.history });
    }

    return {
        ...INITIAL_MORPH_STATE,
        held: readSavedHeld(),
        setEnd: (end, hash) => {
            const state = get();
            commit(otherEndOf(state, end) === hash ? swappedOf(state) : withSampleAt(state, end, hash));
        },
        swap: () => {
            commit(swappedOf(get()));
        },
        setWeight: (weight) => {
            set({ weight: snapWeight(weight) });
        },
        markRendered: () => {
            set({ renderedWeight: get().weight });
        },
        selectEnd: (end) => {
            set({ selectedEnd: end });
        },
        takeSample: (hash) => {
            const state = get();
            if (state.first === hash || state.second === hash) {
                return;
            }
            const end = state.selectedEnd;
            commit(withSampleAt(state, end, hash));
            if (otherEndOf(state, end) === null) {
                set({ selectedEnd: OTHER_END[end] });
            }
        },
        undo: () => {
            restore(undone(get(), snapshotOf(get())));
        },
        redo: () => {
            restore(redone(get(), snapshotOf(get())));
        },
        forgetHeld: () => {
            const state = get();
            const held = forgotten(state);
            if (held !== state.held) {
                saveHeld(held);
            }
            set({ held });
        },
    };
});
