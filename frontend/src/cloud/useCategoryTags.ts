import { getCategoryTags } from "../api/cloud";
import type { TagSummary } from "../api/curation";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const CATEGORY_TAGS_CACHE_KEY = "category-tags";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** The tags the newest scoring gives as top categories, shared through the request cache alongside them and asked for with them. */
export function useCategoryTags(enabled: boolean): FetchState<readonly TagSummary[]> {
    return useFetch(getCategoryTags, NO_DEPENDENCIES, { cacheKey: CATEGORY_TAGS_CACHE_KEY, enabled });
}
