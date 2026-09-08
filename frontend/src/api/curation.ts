import { requestJson, sendJson } from "./client";
import type { components } from "./schema";

export type AnnotationDecisions = components["schemas"]["AnnotationDecisions"];
export type AnnotationWritten = components["schemas"]["AnnotationWritten"];

/** How far one gesture reaches: this sample alone, or every near-duplicate grouped with it. */
export type AnnotationScope = components["schemas"]["AnnotationSource"];

/** What a sample says when nobody has decided anything about it. */
export const NO_DECISIONS: AnnotationDecisions = { label: null, rating: null, favorite: false };

/**
 * Record the whole state a sample should carry from here on.
 *
 * Every decision travels on every write, so anything left empty is a decision undone; a state
 * saying nothing at all removes the annotation. An emptied label is sent as `null`, blank text
 * being malformed rather than a way to clear one.
 */
export async function setSampleAnnotation(
    sampleHash: string,
    decisions: AnnotationDecisions,
    scope: AnnotationScope,
): Promise<AnnotationWritten> {
    return sendJson<AnnotationWritten>(`/curation/annotations/${sampleHash}`, {
        method: "PUT",
        body: { ...decisions, scope },
    });
}

export async function clearSampleAnnotation(sampleHash: string, scope: AnnotationScope): Promise<AnnotationWritten> {
    return setSampleAnnotation(sampleHash, NO_DECISIONS, scope);
}

export async function getLabelVocabulary(): Promise<readonly string[]> {
    return requestJson<readonly string[]>("/curation/annotations/vocabulary");
}
