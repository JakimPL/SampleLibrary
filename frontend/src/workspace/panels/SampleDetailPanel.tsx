import type { ReactElement } from "react";

import { SampleDetailView } from "../../samples/SampleDetailView";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";

interface FocusedSampleDetailProps {
    readonly sampleHash: string;
}

function FocusedSampleDetail({ sampleHash }: FocusedSampleDetailProps): ReactElement {
    const state = useSampleDetail(sampleHash);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    const { sample, relations } = state.data;
    return <SampleDetailView sample={sample} relations={relations} />;
}

export function SampleDetailPanel(): ReactElement {
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);

    if (focusedSampleHash === null) {
        return <p className="no-selection">No sample focused yet — double-click a sample to see it here.</p>;
    }

    return <FocusedSampleDetail sampleHash={focusedSampleHash} />;
}
