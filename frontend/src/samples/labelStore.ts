import { create } from "zustand";

interface LabelState {
    /** Every label set or cleared in this session, by sample hash; `null` means cleared. */
    readonly labelBySampleHash: Readonly<Record<string, string | null>>;
}

interface LabelActions {
    readonly applyLabel: (sampleHashes: readonly string[], label: string | null) => void;
}

export const INITIAL_LABEL_STATE: LabelState = { labelBySampleHash: {} };

/**
 * What this session has decided, held apart from what the server sent with each row.
 *
 * Labelling reaches rows that are already on screen -- a whole equivalence class at once, spread
 * across a list, a detail panel, and a hover tooltip -- and refetching every one of them to show a
 * change this session just made would be both slow and needless. Every badge reads through here
 * first, so one write updates each of those places at once, and the cached requests behind them
 * are invalidated separately so a later remount still reads the server's own answer.
 */
export const useLabelStore = create<LabelState & LabelActions>()((set) => ({
    ...INITIAL_LABEL_STATE,
    applyLabel: (sampleHashes, label) => {
        set((state) => ({
            labelBySampleHash: {
                ...state.labelBySampleHash,
                ...Object.fromEntries(sampleHashes.map((sampleHash) => [sampleHash, label])),
            },
        }));
    },
}));

/** The label to show for a sample: what this session last set for it, else what the server sent. */
export function useHandLabel(sampleHash: string, serverLabel: string | null): string | null {
    const applied = useLabelStore((state) => state.labelBySampleHash[sampleHash]);
    return applied === undefined ? serverLabel : applied;
}
