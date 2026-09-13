import { describe, expect, it, vi } from "vitest";

import {
    cachedRequest,
    getCachedResult,
    invalidateRequest,
    MAX_CACHED_REQUESTS,
    subscribeRequest,
} from "../../src/shared/requestCache";

describe("cachedRequest", () => {
    it("runs the loader only once for repeated calls under the same key", async () => {
        const loader = vi.fn().mockResolvedValue("data");

        const first = cachedRequest("a", loader);
        const second = cachedRequest("a", loader);

        expect(second).toBe(first);
        await expect(first).resolves.toBe("data");
        expect(loader).toHaveBeenCalledTimes(1);
    });

    it("runs the loader again for a different key", () => {
        const loader = vi.fn().mockResolvedValue("data");

        void cachedRequest("a", loader);
        void cachedRequest("b", loader);

        expect(loader).toHaveBeenCalledTimes(2);
    });

    it("keeps no result for a request that failed", async () => {
        const loader = vi.fn().mockRejectedValue(new Error("boom"));

        await expect(cachedRequest("a", loader)).rejects.toThrow("boom");

        expect(getCachedResult("a")).toBeNull();
    });
});

describe("getCachedResult", () => {
    it("returns null before the request settles", () => {
        void cachedRequest("a", () => new Promise(() => undefined));

        expect(getCachedResult("a")).toBeNull();
    });

    it("returns null for a key nothing has requested yet", () => {
        expect(getCachedResult("unknown")).toBeNull();
    });

    it("returns the settled success result once the request resolves", async () => {
        await cachedRequest("a", () => Promise.resolve("data"));

        expect(getCachedResult("a")).toEqual({ status: "success", data: "data" });
    });
});

describe("a failed or invalidated request", () => {
    it("lets the next caller ask again once a request has failed", async () => {
        const failing = vi.fn().mockRejectedValue(new Error("server restarting"));
        await expect(cachedRequest("flaky", failing)).rejects.toThrow("server restarting");

        const recovered = await cachedRequest("flaky", () => Promise.resolve("back"));

        expect(recovered).toBe("back");
        expect(getCachedResult("flaky")).toEqual({ status: "success", data: "back" });
    });

    it("tells whoever watches a key that it was invalidated", async () => {
        await cachedRequest("watched", () => Promise.resolve(1));
        const listener = vi.fn();
        const unsubscribe = subscribeRequest("watched", listener);

        invalidateRequest("watched");
        unsubscribe();
        invalidateRequest("watched");

        expect(listener).toHaveBeenCalledTimes(1);
    });

    it("keeps at most the bounded number of settled answers, letting the oldest unwatched one go", async () => {
        await cachedRequest("oldest", () => Promise.resolve("first"));
        for (let index = 0; index < MAX_CACHED_REQUESTS; index += 1) {
            await cachedRequest(`filler-${String(index)}`, () => Promise.resolve(index));
        }

        expect(getCachedResult("oldest")).toBeNull();
        expect(getCachedResult(`filler-${String(MAX_CACHED_REQUESTS - 1)}`)).not.toBeNull();
    });
});
