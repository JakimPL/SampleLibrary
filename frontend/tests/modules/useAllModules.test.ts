import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../src/api/modules";
import type { Module } from "../../src/api/modules";
import { BULK_FETCH_PAGE_LIMIT, useAllModules } from "../../src/modules/useAllModules";

const { listModules } = vi.hoisted(() => ({ listModules: vi.fn() }));

vi.mock("../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../src/api/modules");
    return { ...actual, listModules };
});

function buildModule(id: number): Module {
    return {
        hash: `hash-${String(id)}`,
        id,
        title: `Module ${String(id)}`,
        filename: `module-${String(id)}.xm`,
        tracker: "xm",
        channel_count: 4,
        pattern_count: 1,
        instrument_count: 1,
        sample_count: 1,
        file_size: 1024,
        ingested_at: "2026-01-01T00:00:00Z",
    };
}

describe("useAllModules", () => {
    it("pages through the full catalog and merges every page in offset order", async () => {
        listModules.mockImplementation(({ offset }: { offset: number }) => {
            if (offset === 0) {
                return Promise.resolve({
                    items: [buildModule(1), buildModule(2)],
                    total: BULK_FETCH_PAGE_LIMIT + 1,
                    limit: BULK_FETCH_PAGE_LIMIT,
                    offset: 0,
                });
            }
            if (offset === BULK_FETCH_PAGE_LIMIT) {
                return Promise.resolve({
                    items: [buildModule(3)],
                    total: BULK_FETCH_PAGE_LIMIT + 1,
                    limit: BULK_FETCH_PAGE_LIMIT,
                    offset: BULK_FETCH_PAGE_LIMIT,
                });
            }
            throw new Error(`unexpected offset ${String(offset)}`);
        });

        const { result } = renderHook(() => useAllModules());

        await waitFor(() => {
            expect(result.current.status).toBe("success");
        });
        if (result.current.status !== "success") {
            throw new Error("expected success");
        }
        expect(result.current.data.map((module) => module.id)).toEqual([1, 2, 3]);
        expect(listModules).toHaveBeenCalledWith({ limit: BULK_FETCH_PAGE_LIMIT, offset: 0, tracker: null });
        expect(listModules).toHaveBeenCalledWith({
            limit: BULK_FETCH_PAGE_LIMIT,
            offset: BULK_FETCH_PAGE_LIMIT,
            tracker: null,
        });
    });

    it("requests only one page when the whole catalog fits in it", async () => {
        listModules.mockResolvedValue({ items: [buildModule(1)], total: 1, limit: BULK_FETCH_PAGE_LIMIT, offset: 0 });

        const { result } = renderHook(() => useAllModules());

        await waitFor(() => {
            expect(result.current.status).toBe("success");
        });
        expect(listModules).toHaveBeenCalledTimes(1);
    });

    it("surfaces an error when any page fails to load", async () => {
        listModules.mockImplementation(({ offset }: { offset: number }) => {
            if (offset === 0) {
                return Promise.resolve({
                    items: [buildModule(1)],
                    total: BULK_FETCH_PAGE_LIMIT + 1,
                    limit: BULK_FETCH_PAGE_LIMIT,
                    offset: 0,
                });
            }
            return Promise.reject(new Error("network down"));
        });

        const { result } = renderHook(() => useAllModules());

        await waitFor(() => {
            expect(result.current.status).toBe("error");
        });
        if (result.current.status !== "error") {
            throw new Error("expected error");
        }
        expect(result.current.message).toBe("network down");
    });
});
