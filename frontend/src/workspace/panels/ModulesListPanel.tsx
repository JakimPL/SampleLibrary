import type { ReactElement } from "react";
import { useState } from "react";

import type { TrackerFormat } from "../../api/modules";
import { ModulesTable } from "../../modules/ModulesTable";
import { useModuleList } from "../../modules/useModuleList";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";

const PAGE_SIZE = 50;

export function ModulesListPanel(): ReactElement {
    const [offset, setOffset] = useState(0);
    const [tracker, setTracker] = useState<TrackerFormat | null>(null);
    const state = useModuleList({ limit: PAGE_SIZE, offset, tracker });

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    return (
        <ModulesTable
            modules={state.data.items}
            total={state.data.total}
            offset={offset}
            limit={PAGE_SIZE}
            tracker={tracker}
            onOffsetChange={setOffset}
            onTrackerChange={(nextTracker) => {
                setTracker(nextTracker);
                setOffset(0);
            }}
        />
    );
}
