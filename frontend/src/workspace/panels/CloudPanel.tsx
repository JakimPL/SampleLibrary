import { type ReactElement, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { CloudPoint, ModuleCloudPoint } from "../../api/cloud";
import { CloudView } from "../../cloud/CloudView";
import type { CloudEntityPoint } from "../../cloud/geometry";
import { useCloud } from "../../cloud/useCloud";
import { useModuleCloud } from "../../cloud/useModuleCloud";
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
 */
function useActiveCloudPoints(tab: CloudTab): FetchState<readonly CloudEntityPoint[]> {
    const sampleState = useCloud();
    const moduleState = useModuleCloud();

    if (tab === "samples") {
        return sampleState.status === "success"
            ? { status: "success", data: samplePoints(sampleState.data) }
            : sampleState;
    }

    return moduleState.status === "success" ? { status: "success", data: modulePoints(moduleState.data) } : moduleState;
}

export function CloudPanel(): ReactElement {
    const [tab, setTab] = useState<CloudTab>("samples");
    const [hovered, setHovered] = useState<HoveredPoint | null>(null);
    const state = useActiveCloudPoints(tab);
    const navigate = useNavigate();
    const highlighted = useSelectionStore((selection) => selection.highlighted);
    const highlightEntity = useSelectionStore((selection) => selection.highlightEntity);
    const clearHighlight = useSelectionStore((selection) => selection.clearHighlight);

    useEffect(() => {
        setHovered(null);
    }, [tab]);

    function handleSelect(entity: EntityRef): void {
        highlightEntity(entity);
    }

    function handleFocus(entity: EntityRef): void {
        void navigate(entityRoute(entity));
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
                        />
                        {hovered !== null && <CloudHoverTooltip entity={hovered.entity} x={hovered.x} y={hovered.y} />}
                    </>
                )}
            </div>
        </div>
    );
}
