import { create } from "zustand";

interface MorphStripState {
    /** Whether a waveform shows under the strip's row: a lone end's own, or the morph's with its slider. */
    readonly expanded: boolean;
    /** Whether the history of the ends shows: a box under the strip on the workspace, a sheet on a phone. */
    readonly historyShown: boolean;
}

interface MorphStripActions {
    readonly toggleExpanded: () => void;
    readonly toggleHistoryShown: () => void;
    readonly hideHistory: () => void;
}

export const INITIAL_MORPH_STRIP_STATE: MorphStripState = { expanded: false, historyShown: false };

/**
 * How the morph strip under the cloud stands: its waveform opens from the waveform button and its
 * history from the history button, each staying as it was left for the visit.
 */
export const useMorphStripStore = create<MorphStripState & MorphStripActions>((set, get) => ({
    ...INITIAL_MORPH_STRIP_STATE,
    toggleExpanded: () => {
        set({ expanded: !get().expanded });
    },
    toggleHistoryShown: () => {
        set({ historyShown: !get().historyShown });
    },
    hideHistory: () => {
        set({ historyShown: false });
    },
}));
