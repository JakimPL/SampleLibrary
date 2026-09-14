import { useCallback } from "react";

import { getModule, type ModuleDetail } from "../api/modules";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

/** The cache key one module's detail is shared under. */
export function moduleDetailCacheKey(moduleHash: string): string {
    return `module-detail:${moduleHash}`;
}

/** One module with its occurrences, shared under its hash, so a hover and the Module Detail panel ask once between them. */
export function useModule(moduleHash: string): FetchState<ModuleDetail> {
    const loader = useCallback(() => getModule(moduleHash), [moduleHash]);
    return useFetch(loader, [moduleHash], { cacheKey: moduleDetailCacheKey(moduleHash) });
}
