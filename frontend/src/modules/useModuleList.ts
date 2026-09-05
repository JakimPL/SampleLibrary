import { useCallback } from "react";

import { listModules, type ListModulesParams, type ModulePage } from "../api/modules";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export function useModuleList(params: ListModulesParams): FetchState<ModulePage> {
    const loader = useCallback(() => listModules(params), [params]);
    return useFetch(loader, [params.limit, params.offset, params.tracker]);
}
