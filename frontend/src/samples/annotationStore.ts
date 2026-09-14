import { useMemo } from "react";
import { create } from "zustand";

import {
    type AnnotationChanges,
    type AnnotationDecisions,
    type AnnotationsWritten,
    NO_DECISIONS,
} from "../api/curation";
import type { SampleDetail, SampleSummary } from "../api/samples";

/** One change sent and not yet answered, in the order it was sent. */
export interface PendingChange {
    readonly sequence: number;
    readonly changes: AnnotationChanges;
}

interface AnnotationState {
    /** What the server last said each sample decided about in this session holds; `null` means nothing. */
    readonly annotationBySampleHash: Readonly<Record<string, AnnotationDecisions | null>>;
    /** The changes still on their way to the server, per sample they reach. */
    readonly pendingBySampleHash: Readonly<Record<string, readonly PendingChange[]>>;
    /** Why the last change to a sample failed, until the next change to it is sent. */
    readonly errorBySampleHash: Readonly<Record<string, string>>;
}

interface AnnotationActions {
    readonly beginChange: (sequence: number, sampleHashes: readonly string[], changes: AnnotationChanges) => void;
    readonly settleChange: (sequence: number, sampleHashes: readonly string[], written: AnnotationsWritten) => void;
    readonly failChange: (sequence: number, sampleHashes: readonly string[], message: string) => void;
}

export const INITIAL_ANNOTATION_STATE: AnnotationState = {
    annotationBySampleHash: {},
    pendingBySampleHash: {},
    errorBySampleHash: {},
};

function withoutSequence(
    pending: Readonly<Record<string, readonly PendingChange[]>>,
    sampleHashes: readonly string[],
    sequence: number,
): Record<string, readonly PendingChange[]> {
    const reached = new Set(sampleHashes);
    return Object.fromEntries(
        Object.entries(pending)
            .map(([sampleHash, changes]): [string, readonly PendingChange[]] => [
                sampleHash,
                reached.has(sampleHash) ? changes.filter((change) => change.sequence !== sequence) : changes,
            ])
            .filter(([, changes]) => changes.length > 0),
    );
}

/**
 * What this session has decided, held apart from what the server sent with each row.
 *
 * One gesture reaches rows that are already on screen -- a whole equivalence class at once, spread
 * across a list, a detail panel, and a hover tooltip -- and refetching every one of them to show a
 * change this session just made would be both slow and needless. A change shows the moment it is
 * sent, laid over what the server last said, and gives way to the server's answer when it arrives;
 * a change that fails is taken off again, leaving its message beside the sample.
 */
export const useAnnotationStore = create<AnnotationState & AnnotationActions>()((set) => ({
    ...INITIAL_ANNOTATION_STATE,
    beginChange: (sequence, sampleHashes, changes) => {
        set((state) => {
            const reached = new Set(sampleHashes);
            const pendingBySampleHash = {
                ...state.pendingBySampleHash,
                ...Object.fromEntries(
                    sampleHashes.map((sampleHash) => [
                        sampleHash,
                        [...(state.pendingBySampleHash[sampleHash] ?? []), { sequence, changes }],
                    ]),
                ),
            };
            const errorBySampleHash = Object.fromEntries(
                Object.entries(state.errorBySampleHash).filter(([sampleHash]) => !reached.has(sampleHash)),
            );
            return { pendingBySampleHash, errorBySampleHash };
        });
    },
    settleChange: (sequence, sampleHashes, written) => {
        set((state) => {
            const answered = written.samples.map((item) => item.sample_hash);
            return {
                pendingBySampleHash: withoutSequence(
                    state.pendingBySampleHash,
                    [...sampleHashes, ...answered],
                    sequence,
                ),
                annotationBySampleHash: {
                    ...state.annotationBySampleHash,
                    ...Object.fromEntries(written.samples.map((item) => [item.sample_hash, item.annotation])),
                },
            };
        });
    },
    failChange: (sequence, sampleHashes, message) => {
        set((state) => ({
            pendingBySampleHash: withoutSequence(state.pendingBySampleHash, sampleHashes, sequence),
            errorBySampleHash: {
                ...state.errorBySampleHash,
                ...Object.fromEntries(sampleHashes.map((sampleHash) => [sampleHash, message])),
            },
        }));
    },
}));

/** The decisions a sample row carries, as the server last reported them. */
export function decisionsOf(sample: SampleSummary | SampleDetail): AnnotationDecisions {
    return { label: sample.hand_label, rating: sample.rating, favorite: sample.favorite };
}

function recordsADecision(decisions: AnnotationDecisions): boolean {
    return decisions.label !== null || decisions.rating !== null || decisions.favorite;
}

/**
 * What to show for a sample: what the server last said in this session, else what it sent with the
 * row, with every change still on its way laid over it in the order it was made.
 */
export function useSampleAnnotation(sampleHash: string, sent: AnnotationDecisions): AnnotationDecisions | null {
    const confirmed = useAnnotationStore((state) => state.annotationBySampleHash[sampleHash]);
    const pending = useAnnotationStore((state) => state.pendingBySampleHash[sampleHash]);
    const { label, rating, favorite } = sent;
    return useMemo(() => {
        const base = confirmed === undefined ? { label, rating, favorite } : (confirmed ?? NO_DECISIONS);
        const shown = (pending ?? []).reduce<AnnotationDecisions>(
            (decisions, change) => ({ ...decisions, ...change.changes }),
            base,
        );
        return recordsADecision(shown) ? shown : null;
    }, [confirmed, pending, label, rating, favorite]);
}

/** Whether a change to this sample is still on its way to the server. */
export function useIsSavingSample(sampleHash: string): boolean {
    return useAnnotationStore((state) => state.pendingBySampleHash[sampleHash] !== undefined);
}

/** Why the last change to this sample failed, or `null` when it did not. */
export function useAnnotationError(sampleHash: string): string | null {
    return useAnnotationStore((state) => state.errorBySampleHash[sampleHash] ?? null);
}
