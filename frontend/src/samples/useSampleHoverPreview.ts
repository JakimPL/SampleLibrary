import { useCallback } from "react";

import { getSamplePreview, type WaveformPeak } from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export interface SampleHoverPreview {
    readonly displayName: string;
    readonly suggestedLabel: string | null;
    readonly handLabel: string | null;
    readonly peaks: readonly WaveformPeak[];
}

/** The cache key one sample's hover preview is shared under, so a write can drop what it made stale. */
export function sampleHoverCacheKey(sampleHash: string): string {
    return `sample-hover:${sampleHash}`;
}

/**
 * A sample's display name, what it is taken to be, and stored waveform thumbnail, fetched as one preview for
 * the Cloud panel's hover tooltip -- one request as light as a glance, against the detail a
 * Sample Detail panel needs. A sample the thumbnail pass has not reached shows no bars.
 */
export function useSampleHoverPreview(sampleHash: string): FetchState<SampleHoverPreview> {
    const loader = useCallback(async () => {
        const preview = await getSamplePreview(sampleHash);
        return {
            displayName: preview.display_name,
            suggestedLabel: preview.suggested_label,
            handLabel: preview.hand_label,
            peaks: preview.thumbnail ?? [],
        };
    }, [sampleHash]);
    return useFetch(loader, [sampleHash], { cacheKey: sampleHoverCacheKey(sampleHash) });
}
