import { type CloudPoint, getCloud } from "../api/cloud";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export const CLOUD_POINTS_CACHE_KEY = "cloud-points";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** Every sample's point, shared through the request cache: the largest answer the app asks for, fetched once a session. */
export function useCloud(): FetchState<readonly CloudPoint[]> {
    return useFetch(getCloud, NO_DEPENDENCIES, { cacheKey: CLOUD_POINTS_CACHE_KEY });
}
