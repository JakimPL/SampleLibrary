import { useEffect, useState } from "react";

import { describeError, type FetchState } from "./fetchState";
import { cachedRequest, getCachedResult } from "./requestCache";

export interface FetchOptions {
    /** A key the settled result is shared under, so hooks mounted with one key issue one request. */
    readonly cacheKey?: string;
    /** Whether the request runs at all; a hook that is not enabled stays loading and asks for nothing. */
    readonly enabled?: boolean;
}

const NO_OPTIONS: FetchOptions = {};

/**
 * Runs `loader` on mount and whenever `deps` changes, exposing the request's progress as a
 * `FetchState`. When `cacheKey` is given, a settled result already cached under that key (by an
 * earlier call anywhere, under the same key) seeds the very first render directly instead of
 * showing a loading state that would immediately flip to data already on hand; the request itself
 * also runs through the same cache, so two components mounted with the same `cacheKey` share one
 * underlying request rather than issuing it twice. `enabled` holds a request back until it is
 * wanted, which is what lets a panel mount every source it may color by while fetching only the
 * one it shows.
 */
export function useFetch<T>(
    loader: () => Promise<T>,
    deps: readonly unknown[],
    options: FetchOptions = NO_OPTIONS,
): FetchState<T> {
    const { cacheKey, enabled = true } = options;
    const [state, setState] = useState<FetchState<T>>(
        () => (cacheKey !== undefined ? getCachedResult<T>(cacheKey) : null) ?? { status: "loading" },
    );

    useEffect(() => {
        if (!enabled) {
            return undefined;
        }
        let active = true;
        const seeded = cacheKey !== undefined ? getCachedResult<T>(cacheKey) : null;
        if (seeded === null) {
            setState({ status: "loading" });
        }
        const request = cacheKey !== undefined ? cachedRequest(cacheKey, loader) : loader();
        request
            .then((data) => {
                if (active) {
                    setState({ status: "success", data });
                }
            })
            .catch((error: unknown) => {
                if (active) {
                    setState({ status: "error", message: describeError(error) });
                }
            });
        return (): void => {
            active = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps -- `deps` is the caller-chosen dependency array
    }, [...deps, enabled]);

    return state;
}
