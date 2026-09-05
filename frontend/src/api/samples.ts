import { requestJson } from "./client";
import type { components } from "./schema";

export type SampleDetail = components["schemas"]["SampleDetail"];
export type SampleRelation = components["schemas"]["SampleRelation"];

export async function getSample(sampleHash: string): Promise<SampleDetail> {
    return requestJson<SampleDetail>(`/samples/${sampleHash}`);
}

export async function getSampleRelations(sampleHash: string): Promise<readonly SampleRelation[]> {
    return requestJson<readonly SampleRelation[]>(`/samples/${sampleHash}/relations`);
}
