import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { cachedRequest } from "../../src/shared/requestCache";
import { useFetch } from "../../src/shared/useFetch";

describe("useFetch", () => {
    it("transitions from loading to success", async () => {
        const { result } = renderHook(() => useFetch(() => Promise.resolve("data"), []));

        expect(result.current).toEqual({ status: "loading" });

        await waitFor(() => {
            expect(result.current).toEqual({ status: "success", data: "data" });
        });
    });

    it("transitions from loading to error, describing the failure", async () => {
        const { result } = renderHook(() => useFetch(() => Promise.reject(new Error("boom")), []));

        await waitFor(() => {
            expect(result.current).toEqual({ status: "error", message: "boom" });
        });
    });

    it("seeds directly from a cache hit under cacheKey, skipping the loading state entirely", async () => {
        await cachedRequest("sample-a", () => Promise.resolve("cached data"));

        const { result } = renderHook(() => useFetch(() => Promise.resolve("fresh data"), [], "sample-a"));

        expect(result.current).toEqual({ status: "success", data: "cached data" });
    });

    it("shares one request across two hooks mounted with the same cacheKey", () => {
        const loader = vi.fn().mockReturnValue(new Promise(() => undefined));

        renderHook(() => useFetch(loader, [], "shared-key"));
        renderHook(() => useFetch(loader, [], "shared-key"));

        expect(loader).toHaveBeenCalledTimes(1);
    });
});
