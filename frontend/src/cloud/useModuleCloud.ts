import { getModuleCloud, type ModuleCloudPoint } from "../api/cloud";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const MODULE_CLOUD_CACHE_KEY = "module-cloud";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** Every module's point, shared through the request cache the way the samples' are. */
export function useModuleCloud(): FetchState<readonly ModuleCloudPoint[]> {
    return useFetch(getModuleCloud, NO_DEPENDENCIES, { cacheKey: MODULE_CLOUD_CACHE_KEY });
}
