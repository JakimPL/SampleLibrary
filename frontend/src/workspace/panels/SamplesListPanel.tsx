import type { ReactElement } from "react";

import { SamplesTable } from "../../samples/SamplesTable";
import { useWindowedSamples } from "../../samples/useWindowedSamples";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";

export function SamplesListPanel(): ReactElement {
    const state = useWindowedSamples();

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error" && state.items.length === 0) {
        return <ErrorNotice message={state.message ?? "Unknown error"} />;
    }

    return (
        <SamplesTable
            samples={state.items}
            total={state.total}
            hasMore={state.hasMore}
            isLoadingMore={state.isLoadingMore}
            onLoadMore={state.loadMore}
            loadMoreError={state.status === "error" ? state.message : null}
        />
    );
}
