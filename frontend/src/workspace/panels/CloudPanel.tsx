import { type ReactElement, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { CloudPoint, ModuleCloudPoint } from "../../api/cloud";
import { CloudView } from "../../cloud/CloudView";
import type { CloudEntityPoint } from "../../cloud/geometry";
import { useCloud } from "../../cloud/useCloud";
import { useModuleCloud } from "../../cloud/useModuleCloud";
import { useAudioPreview } from "../../samples/useAudioPreview";
import { ErrorNotice } from "../../shared/ErrorNotice";
import type { FetchState } from "../../shared/fetchState";
import { Loading } from "../../shared/Loading";
import { type EntityRef, useSelectionStore } from "../selectionStore";
import { entityRoute } from "../useEntityRowInteractions";
import { CloudHoverTooltip } from "./CloudHoverTooltip";

type CloudTab = "samples" | "modules";

interface HoveredPoint {
    readonly entity: EntityRef;
    readonly x: number;
    readonly y: number;
}

const MODULE_TAB_CAPTION = "Preliminary layout — real positions await a spectral-distance embedding.";

function samplePoints(coordinates: readonly CloudPoint[]): readonly CloudEntityPoint[] {
    return coordinates.map((coordinate) => ({
        ref: { kind: "sample", hash: coordinate.sample_hash },
        x: coordinate.x,
        y: coordinate.y,
    }));
}

function modulePoints(coordinates: readonly ModuleCloudPoint[]): readonly CloudEntityPoint[] {
    return coordinates.map((coordinate) => ({
        ref: { kind: "module", hash: coordinate.module_hash },
        x: coordinate.x,
        y: coordinate.y,
    }));
}

/**
 * Both tabs' coordinates are fetched unconditionally, not only once their tab is first opened --
 * each payload is a handful of floats per entity, cheap enough that switching tabs never has to
 * wait on a request the other tab could have already finished.
 *
 * Each tab's points are memoized on its own fetch state, which `useFetch` only ever replaces once
 * a request genuinely settles again -- otherwise `samplePoints`/`modulePoints` would map a fresh
 * array (and fresh point objects) on every render of this panel, including ones unrelated to the
 * coordinates themselves (a hover, the other tab's own fetch resolving). `CloudView` depends on
 * referential stability here: it redraws its whole scatterplot whenever this array's identity
 * changes, so an unstable identity redraws far more often than the data actually does.
 */
function useActiveCloudPoints(tab: CloudTab): FetchState<readonly CloudEntityPoint[]> {
    const sampleState = useCloud();
    const moduleState = useModuleCloud();

    const samplePointsState = useMemo(
        (): FetchState<readonly CloudEntityPoint[]> =>
            sampleState.status === "success"
                ? { status: "success", data: samplePoints(sampleState.data) }
                : sampleState,
        [sampleState],
    );
    const modulePointsState = useMemo(
        (): FetchState<readonly CloudEntityPoint[]> =>
            moduleState.status === "success"
                ? { status: "success", data: modulePoints(moduleState.data) }
                : moduleState,
        [moduleState],
    );

    return tab === "samples" ? samplePointsState : modulePointsState;
}

export function CloudPanel(): ReactElement {
    const [tab, setTab] = useState<CloudTab>("samples");
    const [hovered, setHovered] = useState<HoveredPoint | null>(null);
    const state = useActiveCloudPoints(tab);
    const navigate = useNavigate();
    const highlighted = useSelectionStore((selection) => selection.highlighted);
    const highlightEntity = useSelectionStore((selection) => selection.highlightEntity);
    const clearHighlight = useSelectionStore((selection) => selection.clearHighlight);
    const setComparisonSample = useSelectionStore((selection) => selection.setComparisonSample);
    const { play } = useAudioPreview();

    useEffect(() => {
        setHovered(null);
    }, [tab]);

    function handleSelect(entity: EntityRef): void {
        highlightEntity(entity);
    }

    // Clicking a point directly is treated as asking to hear it, the same way a Thumbnail's own
    // play button would -- a module has no comparable single occurrence to play, so this is a
    // sample-only interaction and a clicked module point highlights (via handleSelect above)
    // without doing anything else.
    function handleActivate(entity: EntityRef): void {
        if (entity.kind === "sample") {
            play(entity.hash);
        }
    }

    function handleFocus(entity: EntityRef): void {
        void navigate(entityRoute(entity));
    }

    function handleCompare(entity: EntityRef): void {
        if (entity.kind === "sample") {
            setComparisonSample(entity.hash);
        }
    }

    function handleHover(entity: EntityRef | null, screenPosition: readonly [number, number] | null): void {
        setHovered(
            entity !== null && screenPosition !== null ? { entity, x: screenPosition[0], y: screenPosition[1] } : null,
        );
    }

    return (
        <div className="panel-stack">
            <div className="panel-filter">
                <button
                    type="button"
                    aria-pressed={tab === "samples"}
                    onClick={() => {
                        setTab("samples");
                    }}
                >
                    Samples
                </button>
                <button
                    type="button"
                    aria-pressed={tab === "modules"}
                    onClick={() => {
                        setTab("modules");
                    }}
                >
                    Modules
                </button>
            </div>
            {tab === "modules" && <p className="cloud-caption">{MODULE_TAB_CAPTION}</p>}
            <div className="panel-body">
                {state.status === "loading" && <Loading />}
                {state.status === "error" && <ErrorNotice message={state.message} />}
                {state.status === "success" && (
                    <>
                        <CloudView
                            points={state.data}
                            highlighted={highlighted}
                            onSelect={handleSelect}
                            onFocus={handleFocus}
                            onClear={clearHighlight}
                            onHover={handleHover}
                            onCompare={handleCompare}
                            onActivate={handleActivate}
                        />
                        {hovered !== null && <CloudHoverTooltip entity={hovered.entity} x={hovered.x} y={hovered.y} />}
                    </>
                )}
            </div>
        </div>
    );
}
