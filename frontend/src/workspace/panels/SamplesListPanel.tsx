import type { ReactElement } from "react";
import { useState } from "react";

import { SamplesTable } from "../../samples/SamplesTable";
import { useSampleList } from "../../samples/useSampleList";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";

const PAGE_SIZE = 50;

export function SamplesListPanel(): ReactElement {
    const [offset, setOffset] = useState(0);
    const state = useSampleList({ limit: PAGE_SIZE, offset });

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    return (
        <SamplesTable
            samples={state.data.items}
            total={state.data.total}
            offset={offset}
            limit={PAGE_SIZE}
            onOffsetChange={setOffset}
        />
    );
}
