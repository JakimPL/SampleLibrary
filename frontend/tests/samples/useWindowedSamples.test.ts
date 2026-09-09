import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../src/api/samples";
import { type SampleSummary, WHOLE_CATALOG } from "../../src/api/samples";
import { useWindowedSamples, WINDOW_PAGE_LIMIT } from "../../src/samples/useWindowedSamples";

const { listSamples } = vi.hoisted(() => ({ listSamples: vi.fn() }));

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, listSamples };
});

function buildSample(id: number): SampleSummary {
    return {
        hash: `hash-${String(id)}`,
        depth: 16,
        channels: 1,
        frames: 4096,
        occurrence_count: 1,
        display_name: `sample-${String(id)}`,
        category: "uncategorized",
        hand_label: null,
        rating: null,
        favorite: false,
        size_bytes: 8192,
        thumbnail: null,
        playback_rate_hz: null,
        equivalence_class_hash: null,
        equivalence_member_count: 1,
    };
}

describe("useWindowedSamples", () => {
    it("loads the first window on mount", async () => {
        listSamples.mockResolvedValue({
            items: [buildSample(1), buildSample(2)],
            total: 50,
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
        });

        const { result } = renderHook(() => useWindowedSamples(false, WHOLE_CATALOG));

        await waitFor(() => {
            expect(result.current.status).toBe("ready");
        });
        expect(result.current.items).toHaveLength(2);
        expect(result.current.total).toBe(50);
        expect(result.current.hasMore).toBe(true);
        expect(listSamples).toHaveBeenCalledWith({
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
            groupByEquivalence: false,
            selection: WHOLE_CATALOG,
        });
    });

    it("appends the next window when loadMore is called", async () => {
        listSamples.mockResolvedValueOnce({
            items: [buildSample(1)],
            total: 2,
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
        });
        listSamples.mockResolvedValueOnce({
            items: [buildSample(2)],
            total: 2,
            limit: WINDOW_PAGE_LIMIT,
            offset: 1,
        });

        const { result } = renderHook(() => useWindowedSamples(false, WHOLE_CATALOG));
        await waitFor(() => {
            expect(result.current.status).toBe("ready");
        });

        act(() => {
            result.current.loadMore();
        });

        await waitFor(() => {
            expect(result.current.items).toHaveLength(2);
        });
        expect(result.current.hasMore).toBe(false);
        expect(listSamples).toHaveBeenCalledWith({
            limit: WINDOW_PAGE_LIMIT,
            offset: 1,
            groupByEquivalence: false,
            selection: WHOLE_CATALOG,
        });
    });

    it("does not request another window once everything is loaded", async () => {
        listSamples.mockResolvedValue({
            items: [buildSample(1)],
            total: 1,
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
        });

        const { result } = renderHook(() => useWindowedSamples(false, WHOLE_CATALOG));
        await waitFor(() => {
            expect(result.current.hasMore).toBe(false);
        });

        act(() => {
            result.current.loadMore();
        });

        expect(listSamples).toHaveBeenCalledTimes(1);
    });

    it("restarts the window from the first page when groupByEquivalence changes", async () => {
        listSamples.mockResolvedValueOnce({
            items: [buildSample(1)],
            total: 2,
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
        });
        const { result, rerender } = renderHook(
            ({ groupByEquivalence }) => useWindowedSamples(groupByEquivalence, WHOLE_CATALOG),
            {
                initialProps: { groupByEquivalence: false },
            },
        );
        await waitFor(() => {
            expect(result.current.status).toBe("ready");
        });

        listSamples.mockResolvedValueOnce({
            items: [buildSample(2)],
            total: 1,
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
        });
        rerender({ groupByEquivalence: true });

        await waitFor(() => {
            expect(result.current.items).toEqual([buildSample(2)]);
        });
        expect(listSamples).toHaveBeenLastCalledWith({
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
            groupByEquivalence: true,
            selection: WHOLE_CATALOG,
        });
    });

    it("restarts the window when the selection narrows, since it reaches the whole catalog", async () => {
        listSamples.mockResolvedValue({ items: [buildSample(1)], total: 1, limit: WINDOW_PAGE_LIMIT, offset: 0 });
        const { result, rerender } = renderHook(({ selection }) => useWindowedSamples(false, selection), {
            initialProps: { selection: WHOLE_CATALOG },
        });
        await waitFor(() => {
            expect(result.current.status).toBe("ready");
        });

        rerender({ selection: { ...WHOLE_CATALOG, favoritesOnly: true } });

        await waitFor(() => {
            expect(listSamples).toHaveBeenLastCalledWith({
                limit: WINDOW_PAGE_LIMIT,
                offset: 0,
                groupByEquivalence: false,
                selection: { ...WHOLE_CATALOG, favoritesOnly: true },
            });
        });
    });

    it("surfaces an error when the initial window fails to load", async () => {
        listSamples.mockRejectedValue(new Error("network down"));

        const { result } = renderHook(() => useWindowedSamples(false, WHOLE_CATALOG));

        await waitFor(() => {
            expect(result.current.status).toBe("error");
        });
        expect(result.current.message).toBe("network down");
    });
});
