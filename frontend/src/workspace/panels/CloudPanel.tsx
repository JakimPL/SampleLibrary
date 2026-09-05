import type { ReactElement } from "react";
import { useNavigate } from "react-router-dom";

import { CloudView } from "../../cloud/CloudView";
import { useCloud } from "../../cloud/useCloud";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";
import { entityRoute } from "../useEntityRowInteractions";

export function CloudPanel(): ReactElement {
    const state = useCloud();
    const navigate = useNavigate();
    const highlightedSampleHash = useSelectionStore((selection) =>
        selection.highlighted?.kind === "sample" ? selection.highlighted.hash : null,
    );
    const highlightEntity = useSelectionStore((selection) => selection.highlightEntity);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    return (
        <CloudView
            points={state.data}
            highlightedSampleHash={highlightedSampleHash}
            onSelect={(sampleHash) => {
                highlightEntity({ kind: "sample", hash: sampleHash });
            }}
            onFocus={(sampleHash) => {
                void navigate(entityRoute({ kind: "sample", hash: sampleHash }));
            }}
        />
    );
}
