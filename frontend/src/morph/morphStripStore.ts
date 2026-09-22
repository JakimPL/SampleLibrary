import { create } from "zustand";

interface MorphStripState {
    /** Whether the slider and the waveform show under the strip's row once a pair is whole. */
    readonly expanded: boolean;
}

interface MorphStripActions {
    readonly setExpanded: (expanded: boolean) => void;
    readonly toggleExpanded: () => void;
}

export const INITIAL_MORPH_STRIP_STATE: MorphStripState = { expanded: true };

/**
 * How the morph strip under the cloud stands: its body opens by itself with the first whole pair,
 * a choice to hide it lasts the visit, and the player strip's Show can open it from outside.
 */
export const useMorphStripStore = create<MorphStripState & MorphStripActions>((set, get) => ({
    ...INITIAL_MORPH_STRIP_STATE,
    setExpanded: (expanded) => {
        set({ expanded });
    },
    toggleExpanded: () => {
        set({ expanded: !get().expanded });
    },
}));
