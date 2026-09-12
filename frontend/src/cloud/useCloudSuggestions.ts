import { type CloudSuggestion, getCloudSuggestions } from "../api/cloud";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const CLOUD_SUGGESTIONS_CACHE_KEY = "cloud-suggestions";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** The samples' suggested tags, shared through the request cache; a scoring changes only when a pass writes one. */
export function useCloudSuggestions(): FetchState<readonly CloudSuggestion[]> {
    return useFetch(getCloudSuggestions, NO_DEPENDENCIES, CLOUD_SUGGESTIONS_CACHE_KEY);
}
