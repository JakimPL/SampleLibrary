import { create } from "zustand";

export type EntityKind = "sample" | "module";

export interface EntityRef {
    readonly kind: EntityKind;
    readonly hash: string;
}

interface SelectionState {
    readonly highlighted: EntityRef | null;
    readonly focusedSampleHash: string | null;
    readonly focusedModuleHash: string | null;
}

interface SelectionActions {
    readonly highlightEntity: (entity: EntityRef) => void;
    readonly clearHighlight: () => void;
    readonly focusSample: (sampleHash: string) => void;
    readonly focusModule: (moduleHash: string) => void;
}

export const INITIAL_SELECTION_STATE: SelectionState = {
    highlighted: null,
    focusedSampleHash: null,
    focusedModuleHash: null,
};

/**
 * The one cross-panel identity every panel reads from and writes to.
 *
 * `focusedSampleHash` and `focusedModuleHash` are independent slots rather than a single tagged
 * "focused entity", since the Module Detail and Sample Detail panels stay populated at once --
 * focusing a sample must never blank out whichever module the shell is also showing. `highlighted`
 * is a single tagged reference because only one ring or row highlight is shown across the whole
 * shell at a time, and it can be either kind. Focusing an entity also highlights it, so "focus
 * implies highlight" is enforced in exactly one place per kind rather than at every call site.
 */
export const useSelectionStore = create<SelectionState & SelectionActions>((set) => ({
    ...INITIAL_SELECTION_STATE,
    highlightEntity: (entity) => {
        set({ highlighted: entity });
    },
    clearHighlight: () => {
        set({ highlighted: null });
    },
    focusSample: (sampleHash) => {
        set({ focusedSampleHash: sampleHash, highlighted: { kind: "sample", hash: sampleHash } });
    },
    focusModule: (moduleHash) => {
        set({ focusedModuleHash: moduleHash, highlighted: { kind: "module", hash: moduleHash } });
    },
}));
