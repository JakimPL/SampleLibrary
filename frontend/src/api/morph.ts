import { apiUrl, requestJson } from "./client";
import type { components } from "./schema";

export type MorphAvailability = components["schemas"]["MorphAvailability"];
export type MorphServiceStatus = components["schemas"]["MorphServiceStatus"];

/** Where the audio at one point between two samples is served, the weight written as it was snapped. */
export function morphAudioUrl(first: string, second: string, weight: number): string {
    const query = new URLSearchParams({ first, second, weight: String(weight) });
    return apiUrl(`/morph/audio?${query.toString()}`);
}

export async function getMorphStatus(): Promise<MorphAvailability> {
    return requestJson<MorphAvailability>("/morph/status");
}
