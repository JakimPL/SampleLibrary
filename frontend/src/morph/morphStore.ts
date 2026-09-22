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

interface MorphPair {
    readonly first: string | null;
    readonly second: string | null;
    /** The weight of the render on screen, or `null` while no point of this pair's path has been asked for yet. */
    readonly renderedWeight: number | null;
}

interface MorphState extends MorphPair {
    readonly weight: number;
    /** The end that takes every sample tapped next, or `null` while neither is selected. */
    readonly selectedEnd: MorphEnd | null;
}

interface MorphActions {
    readonly join: (anchor: string | null, hash: string) => void;
    /** Makes `hash` the first end by name, letting go of the second when it is the same sample. */
    readonly setFirst: (hash: string) => void;
    /** Makes `hash` the second end by name, letting go of the first when it is the same sample. */
    readonly setSecond: (hash: string) => void;
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

/** The ends as chosen, keeping the drawn render only while the pair it was drawn for stays. */
function pairOf(state: MorphPair, first: string | null, second: string | null): MorphPair {
    const unchanged = first === state.first && second === state.second;
    return { first, second, renderedWeight: unchanged ? state.renderedWeight : null };
}

/** The sample at the end opposite `end`. */
function otherEndOf(state: MorphPair, end: MorphEnd): string | null {
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
 * pair, or closes one that has a first end waiting. `setFirst` and `setSecond` name one end
 * outright, and `clearEnd` lets one go. `swap` mirrors the weight along with the ends, so the
 * audible point stays where it was, and keeps the selected letter. A render belongs to the pair it
 * was drawn for, so any change of the ends drops it.
 */
export const useMorphStore = create<MorphState & MorphActions>((set, get) => ({
    ...INITIAL_MORPH_STATE,
    join: (anchor, hash) => {
        if (anchor === hash) {
            return;
        }
        const state = get();
        if (anchor !== null) {
            set(pairOf(state, anchor, hash));
            return;
        }
        set(
            state.first === null || state.first === hash ? pairOf(state, hash, null) : pairOf(state, state.first, hash),
        );
    },
    setFirst: (hash) => {
        const state = get();
        set(pairOf(state, hash, state.second === hash ? null : state.second));
    },
    setSecond: (hash) => {
        const state = get();
        set(pairOf(state, state.first === hash ? null : state.first, hash));
    },
    clearEnd: (end) => {
        const state = get();
        set(end === "first" ? pairOf(state, null, state.second) : pairOf(state, state.first, null));
    },
    swap: () => {
        const state = get();
        set({ ...pairOf(state, state.second, state.first), weight: snapWeight(1 - state.weight) });
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
        if (state.selectedEnd === "first") {
            state.setFirst(hash);
        } else {
            state.setSecond(hash);
        }
    },
}));
