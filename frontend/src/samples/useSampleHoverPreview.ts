import { useCallback } from "react";

import { getSample, getSampleWaveform, type WaveformPeak } from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export interface SampleHoverPreview {
    readonly displayName: string;
    readonly peaks: readonly WaveformPeak[];
}

/**
 * A sample's display name and waveform peaks, fetched together for the Cloud panel's hover
 * tooltip -- deliberately lighter than `useSampleDetail`, which also loads every occurrence and
 * relation a full Sample Detail panel needs but a transient tooltip does not.
 */
export function useSampleHoverPreview(sampleHash: string): FetchState<SampleHoverPreview> {
    const loader = useCallback(async () => {
        const [sample, peaks] = await Promise.all([getSample(sampleHash), getSampleWaveform(sampleHash)]);
        return { displayName: sample.display_name, peaks };
    }, [sampleHash]);
    return useFetch(loader, [sampleHash], `sample-hover:${sampleHash}`);
}
