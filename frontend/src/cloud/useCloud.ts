import { type CloudPoint, getCloud } from "../api/cloud";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

const NO_DEPENDENCIES: readonly unknown[] = [];

export function useCloud(): FetchState<readonly CloudPoint[]> {
    return useFetch(getCloud, NO_DEPENDENCIES);
}
