import { describe, expect, it, vi } from "vitest";

import { cachedRequest, getCachedResult } from "../../src/shared/requestCache";

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

    it("caches a rejection as an error result rather than throwing out of the cache", async () => {
        const loader = vi.fn().mockRejectedValue(new Error("boom"));

        await expect(cachedRequest("a", loader)).rejects.toThrow("boom");

        expect(getCachedResult("a")).toEqual({ status: "error", message: "boom" });
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
