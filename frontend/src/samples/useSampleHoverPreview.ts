import { useCallback } from "react";

import { getSample, getSampleWaveform, type WaveformPeak } from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";
import type { SampleCategory } from "./category";

export interface SampleHoverPreview {
    readonly displayName: string;
    readonly category: SampleCategory;
    readonly handLabel: string | null;
    readonly peaks: readonly WaveformPeak[];
}

/** The cache key one sample's hover preview is shared under, so a write can drop what it made stale. */
export function sampleHoverCacheKey(sampleHash: string): string {
    return `sample-hover:${sampleHash}`;
}

/**
 * A sample's display name, category, and waveform peaks, fetched together for the Cloud panel's
 * hover tooltip -- deliberately lighter than `useSampleDetail`, which also loads every occurrence
 * and relation a full Sample Detail panel needs but a transient tooltip does not.
 */
export function useSampleHoverPreview(sampleHash: string): FetchState<SampleHoverPreview> {
    const loader = useCallback(async () => {
        const [sample, peaks] = await Promise.all([getSample(sampleHash), getSampleWaveform(sampleHash)]);
        return {
            displayName: sample.display_name,
            category: sample.category,
            handLabel: sample.hand_label,
            peaks,
        };
    }, [sampleHash]);
    return useFetch(loader, [sampleHash], sampleHoverCacheKey(sampleHash));
}
