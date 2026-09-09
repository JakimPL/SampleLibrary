import { useCallback, useState } from "react";

import { type AnnotationDecisions, type AnnotationScope, setSampleAnnotation } from "../api/curation";
import { describeError } from "../shared/fetchState";
import { invalidateRequest } from "../shared/requestCache";
import { useAnnotationStore } from "./annotationStore";
import { sampleDetailCacheKey } from "./useSampleDetail";
import { sampleHoverCacheKey } from "./useSampleHoverPreview";

export const VOCABULARY_CACHE_KEY = "label-vocabulary";

/** The datalist every label field offers the wording already in use through. */
export const VOCABULARY_LIST_ID = "sample-label-vocabulary";

export interface AnnotationWriter {
    /** Record the whole state this sample should carry from here on. */
    readonly write: (decisions: AnnotationDecisions) => void;
    readonly isSaving: boolean;
    readonly message: string | null;
}

function forgetCachedSamples(sampleHashes: readonly string[]): void {
    for (const sampleHash of sampleHashes) {
        invalidateRequest(sampleDetailCacheKey(sampleHash));
        invalidateRequest(sampleHoverCacheKey(sampleHash));
    }
}

/**
 * One place a decision about a sample is written from, wherever it is made.
 *
 * A write reaches as far as ``scope`` says and then tells the session store what it recorded, so
 * every row, badge and panel showing that sample follows at once. The cached requests behind them
 * are dropped in the same breath, which is what lets a later remount read the server's own answer,
 * and the vocabulary is dropped with them so a newly used wording joins the list it is offered from.
 */
export function useAnnotationWriter(sampleHash: string, scope: AnnotationScope): AnnotationWriter {
    const applyAnnotation = useAnnotationStore((state) => state.applyAnnotation);
    const [isSaving, setIsSaving] = useState(false);
    const [message, setMessage] = useState<string | null>(null);

    const write = useCallback(
        (decisions: AnnotationDecisions): void => {
            setIsSaving(true);
            setMessage(null);
            setSampleAnnotation(sampleHash, decisions, scope)
                .then((written) => {
                    applyAnnotation(written.sample_hashes, written.annotation);
                    forgetCachedSamples(written.sample_hashes);
                    invalidateRequest(VOCABULARY_CACHE_KEY);
                })
                .catch((error: unknown) => {
                    setMessage(describeError(error));
                })
                .finally(() => {
                    setIsSaving(false);
                });
        },
        [applyAnnotation, sampleHash, scope],
    );

    return { write, isSaving, message };
}
