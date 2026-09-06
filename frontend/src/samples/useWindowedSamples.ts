import { useCallback, useEffect, useRef, useState } from "react";

import { listSamples, type SampleSummary } from "../api/samples";
import { describeError } from "../shared/fetchState";

// Each sample summary embeds a thumbnail, so fetching the whole catalog at once (unlike Modules)
// would mean tens of megabytes up front; this is the page size for one step of the incremental
// scroll-driven fetch instead.
export const WINDOW_PAGE_LIMIT = 200;

export interface WindowedSamples {
    readonly status: "loading" | "error" | "ready";
    readonly items: readonly SampleSummary[];
    readonly total: number;
    readonly message: string | null;
    readonly isLoadingMore: boolean;
    readonly hasMore: boolean;
    readonly loadMore: () => void;
}

/**
 * Loads samples incrementally, one window at a time, so `SamplesListPanel` can present a
 * continuously-scrollable list over the full catalog without holding every sample's thumbnail in
 * memory at once. Sorting and filtering downstream apply only to the samples already loaded --
 * `hasMore`/`total` let the table show an honest "N of {total} loaded" indicator rather than
 * implying a complete, correctly-ordered view. Toggling `groupByEquivalence` restarts the window
 * from the first page: a class split across two already-loaded windows would otherwise collapse
 * only partially, silently misreporting which rows share an identity.
 */
export function useWindowedSamples(groupByEquivalence: boolean): WindowedSamples {
    const [items, setItems] = useState<readonly SampleSummary[]>([]);
    const [total, setTotal] = useState(0);
    const [status, setStatus] = useState<WindowedSamples["status"]>("loading");
    const [message, setMessage] = useState<string | null>(null);
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const loadingMoreRef = useRef(false);

    useEffect(() => {
        let active = true;
        setStatus("loading");
        setItems([]);
        listSamples({ limit: WINDOW_PAGE_LIMIT, offset: 0, groupByEquivalence })
            .then((page) => {
                if (!active) {
                    return;
                }
                setItems(page.items);
                setTotal(page.total);
                setStatus("ready");
            })
            .catch((error: unknown) => {
                if (!active) {
                    return;
                }
                setMessage(describeError(error));
                setStatus("error");
            });
        return (): void => {
            active = false;
        };
    }, [groupByEquivalence]);

    const hasMore = status === "ready" && items.length < total;

    const loadMore = useCallback((): void => {
        if (loadingMoreRef.current || !hasMore) {
            return;
        }
        loadingMoreRef.current = true;
        setIsLoadingMore(true);
        listSamples({ limit: WINDOW_PAGE_LIMIT, offset: items.length, groupByEquivalence })
            .then((page) => {
                setItems((current) => [...current, ...page.items]);
                setTotal(page.total);
            })
            .catch((error: unknown) => {
                setStatus("error");
                setMessage(describeError(error));
            })
            .finally(() => {
                loadingMoreRef.current = false;
                setIsLoadingMore(false);
            });
    }, [hasMore, items.length, groupByEquivalence]);

    return { status, items, total, message, isLoadingMore, hasMore, loadMore };
}
