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
        suggested_label: null,
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
    it("loads the first window on mount, a short one ending the listing", async () => {
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
        expect(result.current.hasMore).toBe(false);
        expect(listSamples).toHaveBeenCalledWith({
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
            groupByEquivalence: false,
            selection: WHOLE_CATALOG,
        });
    });

    it("appends the next window when loadMore is called", async () => {
        const firstWindow = Array.from({ length: WINDOW_PAGE_LIMIT }, (_, index) => buildSample(index));
        listSamples.mockResolvedValueOnce({
            items: firstWindow,
            total: WINDOW_PAGE_LIMIT + 1,
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
        });
        listSamples.mockResolvedValueOnce({
            items: [buildSample(WINDOW_PAGE_LIMIT)],
            total: WINDOW_PAGE_LIMIT + 1,
            limit: WINDOW_PAGE_LIMIT,
            offset: WINDOW_PAGE_LIMIT,
        });

        const { result } = renderHook(() => useWindowedSamples(false, WHOLE_CATALOG));
        await waitFor(() => {
            expect(result.current.status).toBe("ready");
        });

        act(() => {
            result.current.loadMore();
        });

        await waitFor(() => {
            expect(result.current.items).toHaveLength(WINDOW_PAGE_LIMIT + 1);
        });
        expect(result.current.hasMore).toBe(false);
        expect(listSamples).toHaveBeenCalledWith({
            limit: WINDOW_PAGE_LIMIT,
            offset: WINDOW_PAGE_LIMIT,
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

    it("folds near-duplicates in the app, switching grouping with nothing refetched", async () => {
        const grouped = (id: number, classHash: string): SampleSummary => ({
            ...buildSample(id),
            equivalence_class_hash: classHash,
        });
        listSamples.mockResolvedValueOnce({
            items: [grouped(1, "class-x"), buildSample(2), grouped(3, "class-x")],
            total: 3,
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
        });
        const { result, rerender } = renderHook(
            ({ groupByEquivalence }) => useWindowedSamples(groupByEquivalence, WHOLE_CATALOG),
            { initialProps: { groupByEquivalence: false } },
        );
        await waitFor(() => {
            expect(result.current.status).toBe("ready");
        });
        expect(result.current.items.map((row) => row.hash)).toEqual(["hash-1", "hash-2", "hash-3"]);

        rerender({ groupByEquivalence: true });

        expect(result.current.items.map((row) => row.hash)).toEqual(["hash-1", "hash-2"]);
        expect(result.current.groupCount).toBe(2);
        expect(result.current.loadedCount).toBe(3);
        expect(listSamples).toHaveBeenCalledTimes(1);
        expect(listSamples).toHaveBeenCalledWith(expect.objectContaining({ groupByEquivalence: false }));
    });

    it("asks for the next window at the count of raw rows held, however they fold", async () => {
        const grouped = (id: number): SampleSummary => ({ ...buildSample(id), equivalence_class_hash: "class-y" });
        const firstWindow = Array.from({ length: WINDOW_PAGE_LIMIT }, (_, index) => grouped(index));
        listSamples.mockResolvedValueOnce({ items: firstWindow, total: 500, limit: WINDOW_PAGE_LIMIT, offset: 0 });
        listSamples.mockResolvedValueOnce({
            items: [buildSample(900)],
            total: 500,
            limit: WINDOW_PAGE_LIMIT,
            offset: 200,
        });
        const { result } = renderHook(() => useWindowedSamples(true, WHOLE_CATALOG));
        await waitFor(() => {
            expect(result.current.status).toBe("ready");
        });
        expect(result.current.items).toHaveLength(1);

        act(() => {
            result.current.loadMore();
        });

        await waitFor(() => {
            expect(result.current.loadedCount).toBe(WINDOW_PAGE_LIMIT + 1);
        });
        expect(listSamples).toHaveBeenLastCalledWith(expect.objectContaining({ offset: WINDOW_PAGE_LIMIT }));
        expect(result.current.hasMore).toBe(false);
    });

    it("drops a window that lands after the selection moved on", async () => {
        let resolveStale: (page: unknown) => void = () => undefined;
        listSamples.mockResolvedValueOnce({
            items: Array.from({ length: WINDOW_PAGE_LIMIT }, (_, index) => buildSample(index + 10)),
            total: 900,
            limit: WINDOW_PAGE_LIMIT,
            offset: 0,
        });
        const { result, rerender } = renderHook(({ selection }) => useWindowedSamples(false, selection), {
            initialProps: { selection: WHOLE_CATALOG },
        });
        await waitFor(() => {
            expect(result.current.status).toBe("ready");
        });
        listSamples.mockReturnValueOnce(
            new Promise((resolve) => {
                resolveStale = resolve;
            }),
        );
        listSamples.mockResolvedValueOnce({ items: [buildSample(5)], total: 1, limit: WINDOW_PAGE_LIMIT, offset: 0 });
        act(() => {
            result.current.loadMore();
        });

        rerender({ selection: { ...WHOLE_CATALOG, favoritesOnly: true } });
        await waitFor(() => {
            expect(result.current.items.map((row) => row.hash)).toEqual(["hash-5"]);
        });
        await act(async () => {
            resolveStale({ items: [buildSample(2)], total: 900, limit: WINDOW_PAGE_LIMIT, offset: 1 });
            await Promise.resolve();
        });

        expect(result.current.items.map((row) => row.hash)).toEqual(["hash-5"]);
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
