import { useCallback } from "react";

import type { AnnotationChanges, AnnotationScope, AnnotationsWritten } from "../api/curation";
import { CLOUD_LABELS_CACHE_KEY } from "../cloud/useCloudLabels";
import { invalidateRequest } from "../shared/requestCache";
import { useAnnotationError, useIsSavingSample } from "./annotationStore";
import { queueAnnotationChange } from "./annotationWriteQueue";
import { LABEL_TAGS_CACHE_KEY } from "./useLabelTags";
import { sampleDetailCacheKey } from "./useSampleDetail";
import { samplePreviewCacheKey } from "./useSamplePreview";

export const VOCABULARY_CACHE_KEY = "label-vocabulary";

export interface AnnotationWriter {
    /** Change the decisions this gesture names, leaving the sample's others as they are. */
    readonly change: (changes: AnnotationChanges) => void;
    readonly isSaving: boolean;
    readonly message: string | null;
}

function forgetWhatTheWriteChanged(written: AnnotationsWritten, changes: AnnotationChanges): void {
    for (const item of written.samples) {
        invalidateRequest(sampleDetailCacheKey(item.sample_hash));
        invalidateRequest(samplePreviewCacheKey(item.sample_hash));
    }
    if (changes.label !== undefined) {
        invalidateRequest(VOCABULARY_CACHE_KEY);
        invalidateRequest(LABEL_TAGS_CACHE_KEY);
        invalidateRequest(CLOUD_LABELS_CACHE_KEY);
    }
}

/**
 * One place a decision about a sample is written from, wherever it is made.
 *
 * A change reaches as far as `scope` says, in turn with every other change to the same samples, and
 * the session store shows it at once. Once the server has answered, the cached requests describing
 * those samples are dropped, and a new wording also drops the vocabulary, the tag tree and the
 * cloud's labels, so every mounted view asks again and paints the sample by what was just said. A
 * failure is kept beside the sample for whichever view shows it.
 */
export function useAnnotationWriter(sampleHash: string, scope: AnnotationScope): AnnotationWriter {
    const isSaving = useIsSavingSample(sampleHash);
    const message = useAnnotationError(sampleHash);

    const change = useCallback(
        (changes: AnnotationChanges): void => {
            queueAnnotationChange(sampleHash, scope, changes)
                .then((written) => {
                    forgetWhatTheWriteChanged(written, changes);
                })
                .catch(() => undefined);
        },
        [sampleHash, scope],
    );

    return { change, isSaving, message };
}
