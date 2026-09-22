import { create } from "zustand";

interface MorphStripState {
    /** Whether the slider and the waveform show under the strip's row, or the row stands alone. */
    readonly expanded: boolean;
}

interface MorphStripActions {
    readonly setExpanded: (expanded: boolean) => void;
    readonly toggleExpanded: () => void;
}

export const INITIAL_MORPH_STRIP_STATE: MorphStripState = { expanded: false };

/** How the morph strip under the cloud stands, kept where the player strip's Show can open it. */
export const useMorphStripStore = create<MorphStripState & MorphStripActions>((set, get) => ({
    ...INITIAL_MORPH_STRIP_STATE,
    setExpanded: (expanded) => {
        set({ expanded });
    },
    toggleExpanded: () => {
        set({ expanded: !get().expanded });
    },
}));
