import type { ReactElement } from "react";
import { useState } from "react";

import { useLayoutMode } from "../../layout/useLayoutMode";
import { type DetailTab, SampleDetailView } from "../../samples/SampleDetailView";
import { SampleTransport } from "../../samples/SampleTransport";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { withBoundary } from "../../shared/ErrorBoundary";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { hintFor } from "../../shared/hints";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";

const DEFAULT_DETAIL_TAB: DetailTab = "info";

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
        <div className="sample-panel">
            <div className="sample-panel-transport">
                {withBoundary(<SampleTransport key={sample.hash} sample={sample} />)}
            </div>
            <div className="sample-panel-body">
                <SampleDetailView
                    sample={sample}
                    relations={relations}
                    similar={similar}
                    tab={tab}
                    onTabChange={onTabChange}
                />
            </div>
        </div>
    );
}

/**
 * The focused sample in full, from one detail request: its transport at one fixed height, a row's
 * on a phone, over its detail, which scrolls beneath it, the same in the workspace's panel and on
 * the phone's page. The transport keeps a boundary of its own, so a player that fails leaves the
 * detail readable. The detail opens on the sample's own facts, its listings in tabs beside them,
 * and the tab is held here so it outlives each sample's own load.
 */
export function SampleDetailPanel(): ReactElement {
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);
    const [tab, setTab] = useState<DetailTab>(DEFAULT_DETAIL_TAB);
    const { input } = useLayoutMode();

    if (focusedSampleHash === null) {
        return <p className="no-selection">{hintFor("noSample", input)}</p>;
    }

    return <FocusedSampleDetail sampleHash={focusedSampleHash} tab={tab} onTabChange={setTab} />;
}
