import { useCallback } from "react";

import { ApiError } from "../api/client";
import {
    getSample,
    getSampleRelations,
    getSimilarSamples,
    type SampleDetail,
    type SampleRelation,
    type SimilarSample,
} from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

const HTTP_NOT_FOUND = 404;

export interface SampleDetailWithRelations {
    readonly sample: SampleDetail;
    readonly relations: readonly SampleRelation[];
    readonly similar: readonly SimilarSample[];
}

/**
 * A sample has no spectral neighbors to report until an embedding run has persisted its feature
 * vector, which the endpoint reports as a 404 rather than an empty list -- that distinction is
 * collapsed into an honest empty list here, since "not embedded yet" and "no similar samples
 * found" both mean the same thing to this panel.
 */
async function loadSimilarSamples(sampleHash: string): Promise<readonly SimilarSample[]> {
    try {
        return await getSimilarSamples(sampleHash);
    } catch (error: unknown) {
        if (error instanceof ApiError && error.status === HTTP_NOT_FOUND) {
            return [];
        }
        throw error;
    }
}

/**
 * The sample together with its relations and spectral-distance neighbors, cached by sample hash
 * so the Sample Detail and Waveform panels -- both mounted at once, both keyed off the same
 * focused sample -- share one request rather than each fetching it independently.
 */
export function useSampleDetail(sampleHash: string): FetchState<SampleDetailWithRelations> {
    const loader = useCallback(async () => {
        const [sample, relations, similar] = await Promise.all([
            getSample(sampleHash),
            getSampleRelations(sampleHash),
            loadSimilarSamples(sampleHash),
        ]);
        return { sample, relations, similar };
    }, [sampleHash]);
    return useFetch(loader, [sampleHash], `sample-detail:${sampleHash}`);
}
