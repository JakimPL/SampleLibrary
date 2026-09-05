import { requestJson } from "./client";
import type { components } from "./schema";

export type SampleDetail = components["schemas"]["SampleDetail"];
export type SampleSummary = components["schemas"]["SampleSummary"];
export type SamplePage = components["schemas"]["Page_SampleSummary_"];
export type SampleRelation = components["schemas"]["SampleRelation"];
export type WaveformPeak = components["schemas"]["WaveformPeak"];

export interface ListSamplesParams {
    readonly limit: number;
    readonly offset: number;
}

export async function listSamples(params: ListSamplesParams): Promise<SamplePage> {
    const query = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) });
    return requestJson<SamplePage>(`/samples?${query.toString()}`);
}

export async function getSample(sampleHash: string): Promise<SampleDetail> {
    return requestJson<SampleDetail>(`/samples/${sampleHash}`);
}

export async function getSampleRelations(sampleHash: string): Promise<readonly SampleRelation[]> {
    return requestJson<readonly SampleRelation[]>(`/samples/${sampleHash}/relations`);
}

export function sampleAudioUrl(sampleHash: string): string {
    return `/samples/${sampleHash}/audio`;
}
