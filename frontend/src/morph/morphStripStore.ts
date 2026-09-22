import { create } from "zustand";

interface MorphStripState {
    /** Whether a waveform shows under the strip's row: a lone end's own, or the morph's with its slider. */
    readonly expanded: boolean;
}

interface MorphStripActions {
    readonly toggleExpanded: () => void;
}

export const INITIAL_MORPH_STRIP_STATE: MorphStripState = { expanded: false };

/**
 * How the morph strip under the cloud stands: its waveform opens from the waveform button and
 * stays as it was left for the visit.
 */
export const useMorphStripStore = create<MorphStripState & MorphStripActions>((set, get) => ({
    ...INITIAL_MORPH_STRIP_STATE,
    toggleExpanded: () => {
        set({ expanded: !get().expanded });
    },
}));
