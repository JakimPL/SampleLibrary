import type { ReactElement } from "react";

import { useLayoutMode } from "../../layout/useLayoutMode";
import { ModuleDetailView } from "../../modules/ModuleDetailView";
import { useModule } from "../../modules/useModule";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { hintFor } from "../../shared/hints";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";

interface FocusedModuleDetailProps {
    readonly moduleHash: string;
}

function FocusedModuleDetail({ moduleHash }: FocusedModuleDetailProps): ReactElement {
    const state = useModule(moduleHash);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    return <ModuleDetailView module={state.data} />;
}

export function ModuleDetailPanel(): ReactElement {
    const focusedModuleHash = useSelectionStore((state) => state.focusedModuleHash);
    const { input } = useLayoutMode();

    if (focusedModuleHash === null) {
        return <p className="no-selection">{hintFor("noModule", input)}</p>;
    }

    return <FocusedModuleDetail moduleHash={focusedModuleHash} />;
}
