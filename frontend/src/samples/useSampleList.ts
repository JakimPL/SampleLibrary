import { useCallback } from "react";

import { listSamples, type ListSamplesParams, type SamplePage } from "../api/samples";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export function useSampleList(params: ListSamplesParams): FetchState<SamplePage> {
    const loader = useCallback(() => listSamples(params), [params]);
    return useFetch(loader, [params.limit, params.offset]);
}
