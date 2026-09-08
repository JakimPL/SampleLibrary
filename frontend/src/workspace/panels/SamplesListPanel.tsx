import type { ReactElement } from "react";
import { useState } from "react";

import { type SampleSelection, WHOLE_CATALOG } from "../../api/samples";
import { SamplesTable } from "../../samples/SamplesTable";
import { useWindowedSamples } from "../../samples/useWindowedSamples";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";

// Grouping starts on: the equivalence class is the primary identity samples are meant to be
// browsed by, with this toggle offered to see raw per-hash rows on demand.
const GROUP_BY_EQUIVALENCE_DEFAULT = true;

export function SamplesListPanel(): ReactElement {
    const [groupByEquivalence, setGroupByEquivalence] = useState(GROUP_BY_EQUIVALENCE_DEFAULT);
    const [selection, setSelection] = useState<SampleSelection>(WHOLE_CATALOG);
    const state = useWindowedSamples(groupByEquivalence, selection);

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
            groupByEquivalence={groupByEquivalence}
            onGroupByEquivalenceChange={setGroupByEquivalence}
            selection={selection}
            onSelectionChange={setSelection}
        />
    );
}
