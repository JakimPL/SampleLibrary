import { create } from "zustand";

import type { AnnotationDecisions } from "../api/curation";
import type { SampleDetail, SampleSummary } from "../api/samples";

interface AnnotationState {
    /** Every sample decided about in this session, by hash; `null` means every decision was taken back. */
    readonly annotationBySampleHash: Readonly<Record<string, AnnotationDecisions | null>>;
}

interface AnnotationActions {
    readonly applyAnnotation: (sampleHashes: readonly string[], annotation: AnnotationDecisions | null) => void;
}

export const INITIAL_ANNOTATION_STATE: AnnotationState = { annotationBySampleHash: {} };

/**
 * What this session has decided, held apart from what the server sent with each row.
 *
 * One gesture reaches rows that are already on screen -- a whole equivalence class at once, spread
 * across a list, a detail panel, and a hover tooltip -- and refetching every one of them to show a
 * change this session just made would be both slow and needless. The list keeps its own accumulated
 * window and never reads the shared request cache, so this store is the only path a write has back
 * to a visible row. Every badge and star reads through here first, and the cached requests behind
 * them are invalidated separately so a later remount still reads the server's own answer.
 */
export const useAnnotationStore = create<AnnotationState & AnnotationActions>()((set) => ({
    ...INITIAL_ANNOTATION_STATE,
    applyAnnotation: (sampleHashes, annotation) => {
        set((state) => ({
            annotationBySampleHash: {
                ...state.annotationBySampleHash,
                ...Object.fromEntries(sampleHashes.map((sampleHash) => [sampleHash, annotation])),
            },
        }));
    },
}));

/** The decisions a sample row carries, as the server last reported them. */
export function decisionsOf(sample: SampleSummary | SampleDetail): AnnotationDecisions {
    return { label: sample.hand_label, rating: sample.rating, favorite: sample.favorite };
}

/** What to show for a sample: what this session last decided for it, else what the server sent. */
export function useSampleAnnotation(sampleHash: string, sent: AnnotationDecisions): AnnotationDecisions | null {
    const applied = useAnnotationStore((state) => state.annotationBySampleHash[sampleHash]);
    return applied === undefined ? sent : applied;
}
