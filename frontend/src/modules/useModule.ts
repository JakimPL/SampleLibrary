import { useCallback } from "react";

import { getModule, type ModuleDetail } from "../api/modules";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export function useModule(moduleHash: string): FetchState<ModuleDetail> {
    const loader = useCallback(() => getModule(moduleHash), [moduleHash]);
    return useFetch(loader, [moduleHash]);
}
