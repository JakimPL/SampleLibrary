import type { ReactElement } from "react";
import { useEffect, useRef } from "react";
import createScatterplot from "regl-scatterplot";

import type { EntityRef } from "../workspace/selectionStore";
import { type CloudEntityPoint, normalizePoints } from "./geometry";

type Scatterplot = ReturnType<typeof createScatterplot>;

const POINT_SIZE = 4;
const POINT_SIZE_SELECTED = 9;
const POINT_COLOR_PROPERTY = "--text-primary";
const POINT_COLOR_FALLBACK = "#1b1f26";
const SELECTED_COLOR_PROPERTY = "--accent";
const SELECTED_COLOR_FALLBACK = "#a8690f";
const BACKGROUND_COLOR_PROPERTY = "--surface-0";
const BACKGROUND_COLOR_FALLBACK = "#f4f5f7";

interface CloudViewProps {
    readonly points: readonly CloudEntityPoint[];
    readonly highlighted: EntityRef | null;
    readonly onSelect: (entity: EntityRef) => void;
    readonly onFocus: (entity: EntityRef) => void;
}

function readThemeColor(propertyName: string, fallback: string): string {
    const value = getComputedStyle(document.documentElement).getPropertyValue(propertyName).trim();
    return value === "" ? fallback : value;
}

function sameEntity(a: EntityRef, b: EntityRef): boolean {
    return a.kind === b.kind && a.hash === b.hash;
}

/**
 * Renders sample or module positions as a WebGL scatterplot, generic over which kind of entity
 * each point names -- the same component and picking contract serves both the Samples and Modules
 * cloud tabs. Owns regl-scatterplot as this codebase's one file touching that library's own API,
 * mirroring how `useWaveformPlayer.ts` owns wavesurfer.js's.
 *
 * A single click selects the point under the cursor through regl-scatterplot's own hit-testing.
 * regl-scatterplot's own double-click behaviour only deselects, so this view disables it
 * (`deselectOnDblClick: false`) and focuses the hovered point on a native double-click instead,
 * looked up through the library's continuous `pointOver`/`pointOut` hover tracking.
 */
export function CloudView({ points: rawPoints, highlighted, onSelect, onFocus }: CloudViewProps): ReactElement {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const scatterplotRef = useRef<Scatterplot | null>(null);
    const pointsRef = useRef<readonly CloudEntityPoint[]>([]);
    const hoveredIndexRef = useRef<number | null>(null);
    const onSelectRef = useRef(onSelect);
    const onFocusRef = useRef(onFocus);
    onSelectRef.current = onSelect;
    onFocusRef.current = onFocus;

    const points = normalizePoints(rawPoints);
    pointsRef.current = points;

    useEffect(() => {
        const container = containerRef.current;
        if (container === null) {
            return undefined;
        }

        const canvas = document.createElement("canvas");
        container.append(canvas);

        const scatterplot = createScatterplot({
            canvas,
            pointColor: readThemeColor(POINT_COLOR_PROPERTY, POINT_COLOR_FALLBACK),
            pointColorActive: readThemeColor(SELECTED_COLOR_PROPERTY, SELECTED_COLOR_FALLBACK),
            backgroundColor: readThemeColor(BACKGROUND_COLOR_PROPERTY, BACKGROUND_COLOR_FALLBACK),
            pointSize: POINT_SIZE,
            pointSizeSelected: POINT_SIZE_SELECTED,
            deselectOnDblClick: false,
        });
        scatterplotRef.current = scatterplot;

        const selectSubscription = scatterplot.subscribe("select", ({ points: selectedIndices }) => {
            const index = selectedIndices[0];
            const entity = index === undefined ? undefined : pointsRef.current[index]?.ref;
            if (entity !== undefined) {
                onSelectRef.current(entity);
            }
        });
        const pointOverSubscription = scatterplot.subscribe("pointOver", (index) => {
            hoveredIndexRef.current = index;
        });
        const pointOutSubscription = scatterplot.subscribe("pointOut", () => {
            hoveredIndexRef.current = null;
        });

        function handleDoubleClick(): void {
            const index = hoveredIndexRef.current;
            const entity = index === null ? undefined : pointsRef.current[index]?.ref;
            if (entity !== undefined) {
                onFocusRef.current(entity);
            }
        }

        canvas.addEventListener("dblclick", handleDoubleClick);

        return (): void => {
            canvas.removeEventListener("dblclick", handleDoubleClick);
            scatterplot.unsubscribe(selectSubscription);
            scatterplot.unsubscribe(pointOverSubscription);
            scatterplot.unsubscribe(pointOutSubscription);
            scatterplot.destroy();
            scatterplotRef.current = null;
            canvas.remove();
        };
        // Created once per mount; point and highlight updates flow through the effect below rather
        // than recreating the whole WebGL context.
    }, []);

    useEffect(() => {
        const scatterplot = scatterplotRef.current;
        if (scatterplot === null) {
            return;
        }

        void scatterplot.draw(points.map((point) => [point.x, point.y]));
        const highlightedIndex =
            highlighted === null ? -1 : points.findIndex((point) => sameEntity(point.ref, highlighted));
        if (highlightedIndex >= 0) {
            scatterplot.select([highlightedIndex], { preventEvent: true });
        } else {
            scatterplot.deselect({ preventEvent: true });
        }
    }, [points, highlighted]);

    return (
        <div className="cloud-wrap">
            <div className="cloud-canvas" ref={containerRef} />
            {points.length === 0 && (
                <div className="cloud-empty">
                    <h4>No cloud coordinates yet</h4>
                    <p>Run the embedding pipeline to populate this view with positions.</p>
                </div>
            )}
        </div>
    );
}
