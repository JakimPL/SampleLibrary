import { useCallback } from "react";

import { getSample, getSampleRelations, type SampleDetail, type SampleRelation } from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export interface SampleDetailWithRelations {
    readonly sample: SampleDetail;
    readonly relations: readonly SampleRelation[];
}

export function useSampleDetail(sampleHash: string): FetchState<SampleDetailWithRelations> {
    const loader = useCallback(async () => {
        const [sample, relations] = await Promise.all([getSample(sampleHash), getSampleRelations(sampleHash)]);
        return { sample, relations };
    }, [sampleHash]);
    return useFetch(loader, [sampleHash]);
}
