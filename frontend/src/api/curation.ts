import { requestJson, sendJson } from "./client";
import type { components } from "./schema";

export type AnnotationDecisions = components["schemas"]["AnnotationDecisions"];
export type AnnotationsWritten = components["schemas"]["AnnotationsWritten"];

/** How far one gesture reaches: this sample alone, or every near-duplicate grouped with it. */
export type AnnotationScope = components["schemas"]["AnnotationSource"];
/** One tag in use: its path, how many samples carry it, and the rank that stays with it. */
export type TagSummary = components["schemas"]["TagSummary"];
/** The decisions one gesture changes; a decision left out stays as the sample holds it. */
export type AnnotationChanges = Partial<AnnotationDecisions>;

/** What a sample says when nobody has decided anything about it. */
export const NO_DECISIONS: AnnotationDecisions = { label: null, rating: null, favorite: false };

/**
 * Change the decisions one gesture names, on this sample or across its near-duplicates.
 *
 * Every reached sample keeps whatever the change leaves out, so a star click leaves the label a
 * moment-earlier gesture gave it. A decision is cleared by sending `null`, or `false` for the
 * favorite mark; an emptied label is sent as `null`, blank text being malformed rather than a way to
 * clear one.
 */
export async function changeSampleAnnotation(
    sampleHash: string,
    scope: AnnotationScope,
    changes: AnnotationChanges,
): Promise<AnnotationsWritten> {
    return sendJson<AnnotationsWritten>(`/curation/annotations/${sampleHash}`, {
        method: "PATCH",
        body: { ...changes, scope },
    });
}

export async function getLabelVocabulary(): Promise<readonly string[]> {
    return requestJson<readonly string[]>("/curation/annotations/vocabulary");
}

/** Every tag inside the labels, as a tree with a count at each node, most used first. */
export async function getLabelTags(): Promise<readonly TagSummary[]> {
    return requestJson<readonly TagSummary[]>("/curation/annotations/tags");
}
