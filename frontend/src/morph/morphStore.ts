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
    /** The end that takes every sample tapped next, or `null` while neither is selected. */
    readonly selectedEnd: MorphEnd | null;
}

interface MorphActions {
    readonly join: (anchor: string | null, hash: string) => void;
    /** Makes `hash` the sample at `end`; a sample already at the other end trades places with it, the weight mirrored. */
    readonly setEnd: (end: MorphEnd, hash: string) => void;
    /** Lets one end go and keeps the other. */
    readonly clearEnd: (end: MorphEnd) => void;
    readonly swap: () => void;
    readonly setWeight: (weight: number) => void;
    /** Records the current weight as the point whose render is on screen. */
    readonly markRendered: () => void;
    readonly clear: () => void;
    /** Selects an end, or lets the selection go when that end already holds it. */
    readonly toggleSelectedEnd: (end: MorphEnd) => void;
    readonly deselectEnd: () => void;
    /**
     * Gives a tapped sample to the selected end, which stays selected; a sample already at the
     * other end trades places with it. With no end selected the pair stands as it is.
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
    selectedEnd: null,
    ...EMPTY_HISTORY,
};

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
export function otherEndOf(state: MorphPair, end: MorphEnd): string | null {
    return end === "first" ? state.second : state.first;
}

/** The ends traded, with the weight mirrored so the audible point stays where it was. */
function swappedOf(state: MorphSnapshot): MorphSnapshot {
    return pairOf(state, state.second, state.first, snapWeight(1 - state.weight));
}

/**
 * The pair a morph runs between, how far along it the listener stands, which point of the path is
 * drawn on screen, and which end is selected to take the next sample. The strip under the cloud
 * and the marker on the cloud share it, so the two are one control. The pair is its own state,
 * filled by the slots and by the pairing gestures, so it stays where it was put while the shell's
 * highlight and focus move on.
 *
 * A selected end takes every sample tapped in a list or on the cloud, through `takeSample`, until
 * it is deselected; `join` is the gestures' way: the anchor, the sample already in view, becomes
 * the first end and the newly chosen one the second; with no anchor the chosen sample opens a
 * pair, or closes one that has a first end waiting. `setEnd` names one end outright, which is how
 * an empty slot at rest takes the sample in hand and how a row of the history gives its sample
 * back, and `clearEnd` lets one go. `swap` mirrors the weight along with the ends, so the audible
 * point stays where it was, and keeps the selected letter. A render belongs to the pair it was
 * drawn for, so any change of the ends drops it.
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
        join: (anchor, hash) => {
            if (anchor === hash) {
                return;
            }
            const state = get();
            if (anchor !== null) {
                commit(pairOf(state, anchor, hash, state.weight));
                return;
            }
            commit(
                state.first === null || state.first === hash
                    ? pairOf(state, hash, null, state.weight)
                    : pairOf(state, state.first, hash, state.weight),
            );
        },
        setEnd: (end, hash) => {
            const state = get();
            if (otherEndOf(state, end) === hash) {
                commit(swappedOf(state));
                return;
            }
            commit(
                end === "first"
                    ? pairOf(state, hash, state.second, state.weight)
                    : pairOf(state, state.first, hash, state.weight),
            );
        },
        clearEnd: (end) => {
            const state = get();
            commit(
                end === "first"
                    ? pairOf(state, null, state.second, state.weight)
                    : pairOf(state, state.first, null, state.weight),
            );
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
        clear: () => {
            commit(pairOf(get(), null, null, DEFAULT_WEIGHT));
            set({ selectedEnd: null });
        },
        toggleSelectedEnd: (end) => {
            set({ selectedEnd: get().selectedEnd === end ? null : end });
        },
        deselectEnd: () => {
            set({ selectedEnd: null });
        },
        takeSample: (hash) => {
            const state = get();
            if (state.selectedEnd !== null) {
                state.setEnd(state.selectedEnd, hash);
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
