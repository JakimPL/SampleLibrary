import { listModules, type Module } from "../api/modules";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

const NO_DEPENDENCIES: readonly unknown[] = [];

// The largest page sampleserver accepts in one request (`MAX_PAGE_LIMIT` in
// `sampleserver/pagination.py`); fetching the whole catalog means paging at this size rather than
// making one request per default-sized page.
export const BULK_FETCH_PAGE_LIMIT = 500;

async function fetchAllModules(): Promise<readonly Module[]> {
    const firstPage = await listModules({ limit: BULK_FETCH_PAGE_LIMIT, offset: 0, tracker: null });
    const remainingOffsets: number[] = [];
    for (let offset = BULK_FETCH_PAGE_LIMIT; offset < firstPage.total; offset += BULK_FETCH_PAGE_LIMIT) {
        remainingOffsets.push(offset);
    }

    const remainingPages = await Promise.all(
        remainingOffsets.map((offset) => listModules({ limit: BULK_FETCH_PAGE_LIMIT, offset, tracker: null })),
    );

    return [firstPage, ...remainingPages].flatMap((page) => page.items);
}

/**
 * Fetches every module in the catalog in one logical call, paging underneath as needed. Modules
 * are small scalar records -- at full catalog scale the complete set is well under a megabyte --
 * so fetching them all up front lets `ModulesTable` sort and filter instantly over the whole
 * catalog instead of only the currently-loaded page.
 */
export function useAllModules(): FetchState<readonly Module[]> {
    return useFetch(fetchAllModules, NO_DEPENDENCIES);
}
