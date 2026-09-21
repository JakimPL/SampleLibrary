import { type CloudCategory, getCloudCategories } from "../api/cloud";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const CLOUD_CATEGORIES_CACHE_KEY = "cloud-categories";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** Each sample's top category, shared through the request cache and asked for once wanted; a scoring changes only when a pass writes one. */
export function useCloudCategories(enabled: boolean): FetchState<readonly CloudCategory[]> {
    return useFetch(getCloudCategories, NO_DEPENDENCIES, { cacheKey: CLOUD_CATEGORIES_CACHE_KEY, enabled });
}
