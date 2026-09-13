import type { ReactElement } from "react";
import { useState } from "react";

import { type DetailTab, SampleDetailView } from "../../samples/SampleDetailView";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";

const DEFAULT_DETAIL_TAB: DetailTab = "occurrences";

interface FocusedSampleDetailProps {
    readonly sampleHash: string;
    readonly tab: DetailTab;
    readonly onTabChange: (tab: DetailTab) => void;
}

function FocusedSampleDetail({ sampleHash, tab, onTabChange }: FocusedSampleDetailProps): ReactElement {
    const state = useSampleDetail(sampleHash);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    const { sample, relations, similar } = state.data;
    return (
        <SampleDetailView sample={sample} relations={relations} similar={similar} tab={tab} onTabChange={onTabChange} />
    );
}

/** The focused sample in full, with the listing tab held here so it outlives each sample's own load. */
export function SampleDetailPanel(): ReactElement {
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);
    const [tab, setTab] = useState<DetailTab>(DEFAULT_DETAIL_TAB);

    if (focusedSampleHash === null) {
        return <p className="no-selection">No sample selected yet — double-click a sample to see it here.</p>;
    }

    return <FocusedSampleDetail sampleHash={focusedSampleHash} tab={tab} onTabChange={setTab} />;
}
