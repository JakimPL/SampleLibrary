import type { ReactElement } from "react";

import { ModulesTable } from "../../modules/ModulesTable";
import { useAllModules } from "../../modules/useAllModules";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";

export function ModulesListPanel(): ReactElement {
    const state = useAllModules();

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    return <ModulesTable modules={state.data} />;
}
