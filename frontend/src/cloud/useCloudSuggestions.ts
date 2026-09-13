import { type CloudSuggestion, getCloudSuggestions } from "../api/cloud";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const CLOUD_SUGGESTIONS_CACHE_KEY = "cloud-suggestions";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** The samples' first suggested tags, shared through the request cache and asked for once wanted; a scoring changes only when a pass writes one. */
export function useCloudSuggestions(enabled: boolean): FetchState<readonly CloudSuggestion[]> {
    return useFetch(getCloudSuggestions, NO_DEPENDENCIES, { cacheKey: CLOUD_SUGGESTIONS_CACHE_KEY, enabled });
}
