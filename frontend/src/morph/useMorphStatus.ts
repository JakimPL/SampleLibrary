import { useCallback, useEffect } from "react";

import { getMorphStatus, type MorphAvailability } from "../api/morph";
import type { FetchState } from "../shared/fetchState";
import { invalidateRequest } from "../shared/requestCache";
import { useFetch } from "../shared/useFetch";

export const MORPH_STATUS_CACHE_KEY = "morph-status";
export const MORPH_STATUS_RETRY_MS = 15_000;

export interface MorphStatus {
    readonly state: FetchState<MorphAvailability>;
    readonly available: boolean;
    readonly refresh: () => void;
}

/**
 * Whether morphs can be rendered right now, shared by every view that plays one. Asked once for all
 * of them, again on request, and again every little while as long as no inference process answers,
 * since one may be started after the app is open; a request that fails reads as the process being
 * away, which is what a listener needs to know either way.
 */
export function useMorphStatus(): MorphStatus {
    const state = useFetch(getMorphStatus, [], { cacheKey: MORPH_STATUS_CACHE_KEY });
    const available = state.status === "success" && state.data.available;
    const refresh = useCallback(() => {
        invalidateRequest(MORPH_STATUS_CACHE_KEY);
    }, []);

    useEffect(() => {
        if (state.status === "loading" || available) {
            return undefined;
        }
        const retry = setTimeout(refresh, MORPH_STATUS_RETRY_MS);
        return (): void => {
            clearTimeout(retry);
        };
    }, [state, available, refresh]);

    return { state, available, refresh };
}
