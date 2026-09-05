import { useCallback } from "react";

import {
    getSample,
    getSampleRelations,
    getSampleWaveform,
    type SampleDetail,
    type SampleRelation,
    type WaveformPeak,
} from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export interface SampleDetailWithRelations {
    readonly sample: SampleDetail;
    readonly relations: readonly SampleRelation[];
    readonly waveform: readonly WaveformPeak[];
}

export function useSampleDetail(sampleHash: string): FetchState<SampleDetailWithRelations> {
    const loader = useCallback(async () => {
        const [sample, relations, waveform] = await Promise.all([
            getSample(sampleHash),
            getSampleRelations(sampleHash),
            getSampleWaveform(sampleHash),
        ]);
        return { sample, relations, waveform };
    }, [sampleHash]);
    return useFetch(loader, [sampleHash]);
}
