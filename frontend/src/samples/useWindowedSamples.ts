import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { listSamples, type SampleSelection, type SampleSummary } from "../api/samples";
import { describeError } from "../shared/fetchState";

// Each summary embeds a thumbnail, so the listing arrives one window at a time as it scrolls.
export const WINDOW_PAGE_LIMIT = 200;

export interface WindowedSamples {
    readonly status: "loading" | "error" | "ready";
    readonly items: readonly SampleSummary[];
    readonly loadedCount: number;
    readonly groupCount: number;
    readonly total: number;
    readonly message: string | null;
    readonly isLoadingMore: boolean;
    readonly hasMore: boolean;
    readonly loadMore: () => void;
}

/**
 * The rows of a listing, with every group of near-duplicates folded into its first member in
 * listing order. The member listed first is the one the listing's own order ranks highest, so a
 * group reads as its best-used or best-rated sound; a row belonging to no group passes through.
 */
export function foldByEquivalence(rows: readonly SampleSummary[]): readonly SampleSummary[] {
    const seenClasses = new Set<string>();
    return rows.filter((row) => {
        if (row.equivalence_class_hash === null) {
            return true;
        }
        if (seenClasses.has(row.equivalence_class_hash)) {
            return false;
        }
        seenClasses.add(row.equivalence_class_hash);
        return true;
    });
}

function appendUnseen(current: readonly SampleSummary[], page: readonly SampleSummary[]): readonly SampleSummary[] {
    const seen = new Set(current.map((row) => row.hash));
    return [...current, ...page.filter((row) => !seen.has(row.hash))];
}

/**
 * Loads a listing's raw rows incrementally, one window at a time, so `SamplesListPanel` can present
 * a continuously scrollable list over the full catalog without holding every sample's thumbnail in
 * memory at once. Each window is asked for at the count of raw rows already held, so no row is
 * skipped or repeated however the rows fold; grouping near-duplicates folds the held rows in the
 * app, which lets the toggle switch at once with nothing refetched. Narrowing or reordering through
 * `selection` reaches the whole catalog, so it restarts from the first page, and a window still on
 * its way for the previous selection is dropped when it lands. The listing ends at the first
 * window shorter than asked for, or once every counted row is held.
 */
export function useWindowedSamples(groupByEquivalence: boolean, selection: SampleSelection): WindowedSamples {
    const [rawRows, setRawRows] = useState<readonly SampleSummary[]>([]);
    const [total, setTotal] = useState(0);
    const [exhausted, setExhausted] = useState(false);
    const [status, setStatus] = useState<WindowedSamples["status"]>("loading");
    const [message, setMessage] = useState<string | null>(null);
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const generationRef = useRef(0);
    const loadingMoreRef = useRef(false);

    useEffect(() => {
        generationRef.current += 1;
        const generation = generationRef.current;
        loadingMoreRef.current = false;
        setIsLoadingMore(false);
        setStatus("loading");
        setRawRows([]);
        setExhausted(false);
        listSamples({ limit: WINDOW_PAGE_LIMIT, offset: 0, groupByEquivalence: false, selection })
            .then((page) => {
                if (generation !== generationRef.current) {
                    return;
                }
                setRawRows(appendUnseen([], page.items));
                setTotal(page.total);
                setExhausted(page.items.length < WINDOW_PAGE_LIMIT);
                setStatus("ready");
            })
            .catch((error: unknown) => {
                if (generation !== generationRef.current) {
                    return;
                }
                setMessage(describeError(error));
                setStatus("error");
            });
    }, [selection]);

    const hasMore = status === "ready" && !exhausted && rawRows.length < total;

    const loadMore = useCallback((): void => {
        if (loadingMoreRef.current || !hasMore) {
            return;
        }
        const generation = generationRef.current;
        loadingMoreRef.current = true;
        setIsLoadingMore(true);
        listSamples({ limit: WINDOW_PAGE_LIMIT, offset: rawRows.length, groupByEquivalence: false, selection })
            .then((page) => {
                if (generation !== generationRef.current) {
                    return;
                }
                setRawRows((current) => appendUnseen(current, page.items));
                setTotal(page.total);
                setExhausted(page.items.length < WINDOW_PAGE_LIMIT);
            })
            .catch((error: unknown) => {
                if (generation !== generationRef.current) {
                    return;
                }
                setStatus("error");
                setMessage(describeError(error));
            })
            .finally(() => {
                if (generation !== generationRef.current) {
                    return;
                }
                loadingMoreRef.current = false;
                setIsLoadingMore(false);
            });
    }, [hasMore, rawRows.length, selection]);

    const folded = useMemo(() => foldByEquivalence(rawRows), [rawRows]);

    return {
        status,
        items: groupByEquivalence ? folded : rawRows,
        loadedCount: rawRows.length,
        groupCount: folded.length,
        total,
        message,
        isLoadingMore,
        hasMore,
        loadMore,
    };
}
