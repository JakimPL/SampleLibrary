import { create } from "zustand";

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

interface MorphState extends MorphPair {
    readonly weight: number;
    /** The end that takes every sample tapped next, or `null` while neither is selected. */
    readonly selectedEnd: MorphEnd | null;
}

interface MorphActions {
    readonly join: (anchor: string | null, hash: string) => void;
    /** Makes `hash` the sample at `end` by name, letting go of the other end when it holds the same sample. */
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
}

export const INITIAL_MORPH_STATE: MorphState = {
    first: null,
    second: null,
    weight: DEFAULT_WEIGHT,
    renderedWeight: null,
    selectedEnd: null,
};

/**
 * The ends as chosen: a pair that stays keeps the render drawn for it, a pair just completed is
 * drawn at `weight` before any point of it is heard, and a pair missing an end has nothing drawn.
 */
function pairOf(state: MorphPair, first: string | null, second: string | null, weight: number): MorphPair {
    if (first === state.first && second === state.second) {
        return { first, second, renderedWeight: state.renderedWeight };
    }
    return { first, second, renderedWeight: first !== null && second !== null ? weight : null };
}

/** The sample at the end opposite `end`. */
export function otherEndOf(state: MorphPair, end: MorphEnd): string | null {
    return end === "first" ? state.second : state.first;
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
 * an empty slot at rest takes the sample in hand, and `clearEnd` lets one go. `swap` mirrors the
 * weight along with the ends, so the audible point stays where it was, and keeps the selected
 * letter. A render belongs to the pair it was drawn for, so any change of the ends drops it.
 */
export const useMorphStore = create<MorphState & MorphActions>((set, get) => ({
    ...INITIAL_MORPH_STATE,
    join: (anchor, hash) => {
        if (anchor === hash) {
            return;
        }
        const state = get();
        if (anchor !== null) {
            set(pairOf(state, anchor, hash, state.weight));
            return;
        }
        set(
            state.first === null || state.first === hash
                ? pairOf(state, hash, null, state.weight)
                : pairOf(state, state.first, hash, state.weight),
        );
    },
    setEnd: (end, hash) => {
        const state = get();
        const other = otherEndOf(state, end) === hash ? null : otherEndOf(state, end);
        set(end === "first" ? pairOf(state, hash, other, state.weight) : pairOf(state, other, hash, state.weight));
    },
    clearEnd: (end) => {
        const state = get();
        set(
            end === "first"
                ? pairOf(state, null, state.second, state.weight)
                : pairOf(state, state.first, null, state.weight),
        );
    },
    swap: () => {
        const state = get();
        const weight = snapWeight(1 - state.weight);
        set({ ...pairOf(state, state.second, state.first, weight), weight });
    },
    setWeight: (weight) => {
        set({ weight: snapWeight(weight) });
    },
    markRendered: () => {
        set({ renderedWeight: get().weight });
    },
    clear: () => {
        set(INITIAL_MORPH_STATE);
    },
    toggleSelectedEnd: (end) => {
        set({ selectedEnd: get().selectedEnd === end ? null : end });
    },
    deselectEnd: () => {
        set({ selectedEnd: null });
    },
    takeSample: (hash) => {
        const state = get();
        if (state.selectedEnd === null) {
            return;
        }
        if (otherEndOf(state, state.selectedEnd) === hash) {
            state.swap();
            return;
        }
        state.setEnd(state.selectedEnd, hash);
    },
}));
