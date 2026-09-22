import { create } from "zustand";

const WEIGHT_STEPS = 100;
export const WEIGHT_STEP = 1 / WEIGHT_STEPS;
export const DEFAULT_WEIGHT = 0.5;

/**
 * The weight held to the unit interval and to the grid of hundredths the renderer serves, so a
 * snapped weight writes as one two-place decimal in a URL and names exactly one cached render.
 */
export function snapWeight(weight: number): number {
    const clamped = Math.min(1, Math.max(0, weight));
    return Math.round(clamped * WEIGHT_STEPS) / WEIGHT_STEPS;
}

interface MorphState {
    readonly first: string | null;
    readonly second: string | null;
    readonly weight: number;
}

interface MorphActions {
    readonly join: (anchor: string | null, hash: string) => void;
    /** Makes `hash` the first end by name, letting go of the second when it is the same sample. */
    readonly setFirst: (hash: string) => void;
    /** Makes `hash` the second end by name, letting go of the first when it is the same sample. */
    readonly setSecond: (hash: string) => void;
    readonly swap: () => void;
    readonly setWeight: (weight: number) => void;
    readonly clear: () => void;
}

export const INITIAL_MORPH_STATE: MorphState = {
    first: null,
    second: null,
    weight: DEFAULT_WEIGHT,
};

/**
 * The pair a morph runs between and how far along it the listener stands, shared by the Morph
 * panel's slider and the marker on the cloud so the two are one control. The pair is its own state,
 * set by the pairing gestures alone -- the cloud's right button and a Shift-click on a sample row --
 * so it stays where it was put while the shell's highlight and focus move on.
 *
 * `join` is the cloud's gesture: the anchor, the sample already in view, becomes the first end and
 * the newly chosen one the second; with no anchor the chosen sample opens a pair, or closes one
 * that has a first end waiting. `setFirst` and `setSecond` are the buttons' way, naming one end
 * outright. `swap` mirrors the weight along with the ends, so the audible point stays where it was.
 */
export const useMorphStore = create<MorphState & MorphActions>((set, get) => ({
    ...INITIAL_MORPH_STATE,
    join: (anchor, hash) => {
        if (anchor === hash) {
            return;
        }
        if (anchor !== null) {
            set({ first: anchor, second: hash });
            return;
        }
        const { first } = get();
        set(first === null || first === hash ? { first: hash, second: null } : { second: hash });
    },
    setFirst: (hash) => {
        const { second } = get();
        set({ first: hash, second: second === hash ? null : second });
    },
    setSecond: (hash) => {
        const { first } = get();
        set({ first: first === hash ? null : first, second: hash });
    },
    swap: () => {
        const { first, second, weight } = get();
        set({ first: second, second: first, weight: snapWeight(1 - weight) });
    },
    setWeight: (weight) => {
        set({ weight: snapWeight(weight) });
    },
    clear: () => {
        set({ first: null, second: null, weight: DEFAULT_WEIGHT });
    },
}));
