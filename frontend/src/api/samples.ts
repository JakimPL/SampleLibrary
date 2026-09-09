import { apiUrl, requestJson } from "./client";
import type { components } from "./schema";

export type SampleDetail = components["schemas"]["SampleDetail"];
export type SampleSummary = components["schemas"]["SampleSummary"];
export type SamplePage = components["schemas"]["Page_SampleSummary_"];
export type SampleRelation = components["schemas"]["SampleRelation"];
export type SampleDistance = components["schemas"]["SampleDistance"];
export type SimilarSample = components["schemas"]["SimilarSample"];
export type WaveformPeak = components["schemas"]["WaveformPeak"];
export type SampleSort = components["schemas"]["SampleSort"];

/** Which samples a listing walks, and the order it walks them in. */
export interface SampleSelection {
    readonly favoritesOnly: boolean;
    readonly sort: SampleSort;
}

export const WHOLE_CATALOG: SampleSelection = { favoritesOnly: false, sort: "occurrences" };

export interface ListSamplesParams {
    readonly limit: number;
    readonly offset: number;
    readonly groupByEquivalence: boolean;
    readonly selection: SampleSelection;
}

export async function listSamples(params: ListSamplesParams): Promise<SamplePage> {
    const query = new URLSearchParams({
        limit: String(params.limit),
        offset: String(params.offset),
        group_by_equivalence: String(params.groupByEquivalence),
        favorites_only: String(params.selection.favoritesOnly),
        sort: params.selection.sort,
    });
    return requestJson<SamplePage>(`/samples?${query.toString()}`);
}

export async function getSample(sampleHash: string): Promise<SampleDetail> {
    return requestJson<SampleDetail>(`/samples/${sampleHash}`);
}

export async function getSampleRelations(sampleHash: string): Promise<readonly SampleRelation[]> {
    return requestJson<readonly SampleRelation[]>(`/samples/${sampleHash}/relations`);
}

export async function getSampleDistance(sampleHash: string, otherHash: string): Promise<SampleDistance> {
    return requestJson<SampleDistance>(`/samples/${sampleHash}/distance/${otherHash}`);
}

export async function getSimilarSamples(sampleHash: string): Promise<readonly SimilarSample[]> {
    return requestJson<readonly SimilarSample[]>(`/samples/${sampleHash}/similar`);
}

export async function getSampleWaveform(sampleHash: string): Promise<readonly WaveformPeak[]> {
    return requestJson<readonly WaveformPeak[]>(`/samples/${sampleHash}/waveform`);
}

export function sampleAudioUrl(sampleHash: string): string {
    return apiUrl(`/samples/${sampleHash}/audio`);
}
