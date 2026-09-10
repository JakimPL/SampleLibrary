import { type CloudLabel, getCloudLabels } from "../api/cloud";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const CLOUD_LABELS_CACHE_KEY = "cloud-labels";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** The labeled samples' tags, shared through the request cache and dropped whenever a label is written. */
export function useCloudLabels(): FetchState<readonly CloudLabel[]> {
    return useFetch(getCloudLabels, NO_DEPENDENCIES, CLOUD_LABELS_CACHE_KEY);
}
