import type { FetchState } from "./fetchState";

interface CacheEntry<T> {
    readonly promise: Promise<T>;
    result: FetchState<T> | null;
}

type Listener = () => void;

/** How many settled requests the cache keeps before it lets the least recently asked for go. */
export const MAX_CACHED_REQUESTS = 256;

const cache = new Map<string, CacheEntry<unknown>>();
const listeners = new Map<string, Set<Listener>>();

/**
 * Runs `loader` at most once per `key`: a second call while the first is still in flight, or
 * after it has succeeded, returns the same promise instead of issuing a second request, so two
 * panels focused on the same entity (e.g. Sample Detail and the Waveform panel, both keyed by sample
 * hash) share one request rather than each fetching it independently. A request that fails leaves
 * the cache as it found it, so the next one to ask tries again, as a panel reopened after the server
 * came back does. The cache keeps at most `MAX_CACHED_REQUESTS` settled answers, letting go of the
 * one asked for longest ago that no mounted component is watching.
 */
export function cachedRequest<T>(key: string, loader: () => Promise<T>): Promise<T> {
    const existing = cache.get(key);
    if (existing) {
        cache.delete(key);
        cache.set(key, existing);
        return existing.promise as Promise<T>;
    }

    const entry: CacheEntry<T> = { promise: loader(), result: null };
    entry.promise.then(
        (data) => {
            entry.result = { status: "success", data };
        },
        () => {
            if (cache.get(key) === entry) {
                cache.delete(key);
            }
        },
    );
    cache.set(key, entry);
    letOldestGo();
    return entry.promise;
}

function letOldestGo(): void {
    for (const [key, entry] of cache) {
        if (cache.size <= MAX_CACHED_REQUESTS) {
            return;
        }
        if (entry.result !== null && (listeners.get(key)?.size ?? 0) === 0) {
            cache.delete(key);
        }
    }
}

/** The answer already cached under `key`, or `null` if it has not arrived (or been asked for) yet. */
export function getCachedResult<T>(key: string): FetchState<T> | null {
    return (cache.get(key)?.result as FetchState<T> | null) ?? null;
}

/** Calls `listener` whenever `key` is invalidated, until the returned function is called. */
export function subscribeRequest(key: string, listener: Listener): () => void {
    const watching = listeners.get(key) ?? new Set<Listener>();
    watching.add(listener);
    listeners.set(key, watching);
    return (): void => {
        watching.delete(listener);
        if (watching.size === 0) {
            listeners.delete(key);
        }
    };
}

/**
 * Drops one cached request and tells everything watching it, so a mounted component asks again.
 * Used after a write, where whatever was cached under that key describes the library as it was
 * beforehand.
 */
export function invalidateRequest(key: string): void {
    cache.delete(key);
    for (const listener of [...(listeners.get(key) ?? [])]) {
        listener();
    }
}

/** Drops every cached request. Exists for tests, where each case expects a clean cache. */
export function clearRequestCache(): void {
    cache.clear();
}
