import { describeError, type FetchState } from "./fetchState";

interface CacheEntry<T> {
    readonly promise: Promise<T>;
    result: FetchState<T> | null;
}

const cache = new Map<string, CacheEntry<unknown>>();

/**
 * Runs `loader` at most once per `key`: a second call while the first is still in flight, or
 * after it has settled, returns the same promise instead of issuing a second request. Generalizes
 * the module-level cache `useAudioPreview` already keeps for its own single purpose into a shared
 * one, so two panels focused on the same entity (e.g. Sample Detail and the Waveform panel, both
 * keyed by sample hash) share one request rather than each fetching it independently.
 */
export function cachedRequest<T>(key: string, loader: () => Promise<T>): Promise<T> {
    const existing = cache.get(key);
    if (existing) {
        return existing.promise as Promise<T>;
    }

    const entry: CacheEntry<T> = { promise: loader(), result: null };
    entry.promise.then(
        (data) => {
            entry.result = { status: "success", data };
        },
        (error: unknown) => {
            entry.result = { status: "error", message: describeError(error) };
        },
    );
    cache.set(key, entry);
    return entry.promise;
}

/** The settled result already cached under `key`, or `null` if it has not settled (or run) yet. */
export function getCachedResult<T>(key: string): FetchState<T> | null {
    return (cache.get(key)?.result as FetchState<T> | null) ?? null;
}

/** Drops every cached request. Exists for tests, where each case expects a clean cache. */
export function clearRequestCache(): void {
    cache.clear();
}
