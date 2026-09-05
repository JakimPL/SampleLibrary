import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
