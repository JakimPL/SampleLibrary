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

        const { result } = renderHook(() =>
            useFetch(() => Promise.resolve("fresh data"), [], { cacheKey: "sample-a" }),
        );

        expect(result.current).toEqual({ status: "success", data: "cached data" });
    });

    it("shares one request across two hooks mounted with the same cacheKey", () => {
        const loader = vi.fn().mockReturnValue(new Promise(() => undefined));

        renderHook(() => useFetch(loader, [], { cacheKey: "shared-key" }));
        renderHook(() => useFetch(loader, [], { cacheKey: "shared-key" }));

        expect(loader).toHaveBeenCalledTimes(1);
    });

    it("runs nothing while it is not enabled, and once enabled runs the loader once", async () => {
        const loader = vi.fn().mockResolvedValue("data");

        const { result, rerender } = renderHook(({ enabled }) => useFetch(loader, [], { enabled }), {
            initialProps: { enabled: false },
        });

        expect(loader).not.toHaveBeenCalled();
        expect(result.current).toEqual({ status: "loading" });

        rerender({ enabled: true });

        await waitFor(() => {
            expect(result.current).toEqual({ status: "success", data: "data" });
        });
        expect(loader).toHaveBeenCalledTimes(1);
    });
});
