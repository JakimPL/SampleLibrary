import { getLabelTags, type TagSummary } from "../api/curation";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const LABEL_TAGS_CACHE_KEY = "label-tags";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** The tag tree inside the labels, shared through the request cache and dropped whenever a label is written; asked for once wanted. */
export function useLabelTags(enabled: boolean): FetchState<readonly TagSummary[]> {
    return useFetch(getLabelTags, NO_DEPENDENCIES, { cacheKey: LABEL_TAGS_CACHE_KEY, enabled });
}
