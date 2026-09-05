import type { ReactElement } from "react";

import { getStats } from "../../api/stats";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";
import { useFetch } from "../../shared/useFetch";
import { StatsView } from "../../stats/StatsView";

const NO_DEPENDENCIES: readonly unknown[] = [];

export function StatsPanel(): ReactElement {
    const state = useFetch(getStats, NO_DEPENDENCIES);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    return <StatsView stats={state.data} />;
}
