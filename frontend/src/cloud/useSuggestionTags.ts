import { getSuggestionTags } from "../api/cloud";
import type { TagSummary } from "../api/curation";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const SUGGESTION_TAGS_CACHE_KEY = "suggestion-tags";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** The tags the newest scoring suggests first, shared through the request cache alongside the suggestions and asked for with them. */
export function useSuggestionTags(enabled: boolean): FetchState<readonly TagSummary[]> {
    return useFetch(getSuggestionTags, NO_DEPENDENCIES, { cacheKey: SUGGESTION_TAGS_CACHE_KEY, enabled });
}
