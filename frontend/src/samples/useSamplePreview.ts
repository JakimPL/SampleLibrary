import { useCallback } from "react";

import { getSamplePreview, type SamplePreview } from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

/** The cache key one sample's preview is shared under, so a write can drop what it made stale. */
export function samplePreviewCacheKey(sampleHash: string): string {
    return `sample-preview:${sampleHash}`;
}

/**
 * A glance at a sample: its display name, what it is taken to be, and the waveform thumbnail the
 * catalog stores for it -- one request as light as a glance, against the detail a Sample Detail
 * panel needs.
 *
 * Every view that wants a sample's contour without its audio reads it here, so the cloud's hover
 * tooltip and the morph's traces share one request per sample. A sample the thumbnail pass has not
 * reached carries no thumbnail, and a view drawing one shows no bars.
 */
export function useSamplePreview(sampleHash: string): FetchState<SamplePreview> {
    const loader = useCallback(() => getSamplePreview(sampleHash), [sampleHash]);
    return useFetch(loader, [sampleHash], { cacheKey: samplePreviewCacheKey(sampleHash) });
}
