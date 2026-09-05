import { useCallback } from "react";

import { getSample, getSampleRelations, type SampleDetail, type SampleRelation } from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export interface SampleDetailWithRelations {
    readonly sample: SampleDetail;
    readonly relations: readonly SampleRelation[];
}

/**
 * The sample together with its relations, cached by sample hash so the Sample Detail and Waveform
 * panels -- both mounted at once, both keyed off the same focused sample -- share one request
 * rather than each fetching it independently.
 */
export function useSampleDetail(sampleHash: string): FetchState<SampleDetailWithRelations> {
    const loader = useCallback(async () => {
        const [sample, relations] = await Promise.all([getSample(sampleHash), getSampleRelations(sampleHash)]);
        return { sample, relations };
    }, [sampleHash]);
    return useFetch(loader, [sampleHash], `sample-detail:${sampleHash}`);
}
