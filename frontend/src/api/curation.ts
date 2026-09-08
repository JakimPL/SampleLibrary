import { requestJson, sendJson } from "./client";
import type { components } from "./schema";

export type LabelsWritten = components["schemas"]["LabelsWritten"];

/** How far a labeling reaches: this sample alone, or every near-duplicate grouped with it. */
export type LabelScope = components["schemas"]["LabelSource"];

export async function setSampleLabel(sampleHash: string, label: string, scope: LabelScope): Promise<LabelsWritten> {
    return sendJson<LabelsWritten>(`/curation/labels/${sampleHash}`, { method: "PUT", body: { label, scope } });
}

export async function clearSampleLabel(sampleHash: string, scope: LabelScope): Promise<LabelsWritten> {
    const query = new URLSearchParams({ scope });
    return sendJson<LabelsWritten>(`/curation/labels/${sampleHash}?${query.toString()}`, {
        method: "DELETE",
        body: null,
    });
}

export async function getLabelVocabulary(): Promise<readonly string[]> {
    return requestJson<readonly string[]>("/curation/labels/vocabulary");
}
