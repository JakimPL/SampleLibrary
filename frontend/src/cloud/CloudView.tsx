import type { ReactElement } from "react";
import { useEffect, useRef, useState } from "react";
import createScatterplot from "regl-scatterplot";

import type { EntityRef } from "../workspace/selectionStore";
import { type CloudEntityPoint, normalizePoints } from "./geometry";

type Scatterplot = ReturnType<typeof createScatterplot>;
type ScreenPosition = readonly [number, number];

const POINT_SIZE = 4;
const POINT_SIZE_SELECTED = 9;
const POINT_COLOR_PROPERTY = "--text-primary";
const POINT_COLOR_FALLBACK = "#1b1f26";
const SELECTED_COLOR_PROPERTY = "--accent";
const SELECTED_COLOR_FALLBACK = "#a8690f";
const BACKGROUND_COLOR_PROPERTY = "--surface-0";
const BACKGROUND_COLOR_FALLBACK = "#f4f5f7";

// Kept in step with the ring animations' own total duration in styles.css (two staggered 1400ms
// rings, the second delayed by 300ms) so the marker element is dropped only once both have faded.
const PING_LIFETIME_MS = 1900;

interface CloudViewProps {
    readonly points: readonly CloudEntityPoint[];
    readonly highlighted: EntityRef | null;
    readonly onSelect: (entity: EntityRef) => void;
    readonly onFocus: (entity: EntityRef) => void;
    readonly onClear: () => void;
    readonly onHover: (entity: EntityRef | null, screenPosition: ScreenPosition | null) => void;
}

interface Ping {
    readonly key: number;
    readonly pointIndex: number;
    readonly position: ScreenPosition;
}

function readThemeColor(propertyName: string, fallback: string): string {
    const value = getComputedStyle(document.documentElement).getPropertyValue(propertyName).trim();
    return value === "" ? fallback : value;
}

function sameEntity(a: EntityRef, b: EntityRef): boolean {
    return a.kind === b.kind && a.hash === b.hash;
}

function sameHighlight(a: EntityRef | null, b: EntityRef | null): boolean {
    return a === null || b === null ? a === b : sameEntity(a, b);
}

/**
 * Renders sample or module positions as a WebGL scatterplot, generic over which kind of entity
 * each point names -- the same component and picking contract serves both the Samples and Modules
 * cloud tabs. Owns regl-scatterplot as this codebase's one file touching that library's own API,
 * mirroring how `useWaveformPlayer.ts` owns wavesurfer.js's.
 *
 * A single click selects the point under the cursor through regl-scatterplot's own hit-testing,
 * and clears the shell-wide highlight when the click misses every point. regl-scatterplot's own
 * double-click behaviour only deselects, so this view disables it (`deselectOnDblClick: false`)
 * and focuses the hovered point on a native double-click instead, looked up through the library's
 * continuous `pointOver`/`pointOut` hover tracking -- the same tracking a miss-click reads to tell
 * a hit from empty space, and that `onHover` reports upward for a caller-rendered detail popup.
 * Pressing Escape while the canvas has focus clears the highlight too, through the library's own
 * built-in `deselect` behaviour. Whenever `highlighted` changes to a point present in this view (a
 * click elsewhere in the shell just located a sample or module here), a brief sonar-style ping
 * marks its screen position -- tracking the library's own `view` event so the ping stays pinned to
 * the point through any pan or zoom while it plays, rather than drifting off it.
 */
export function CloudView({
    points: rawPoints,
    highlighted,
    onSelect,
    onFocus,
    onClear,
    onHover,
}: CloudViewProps): ReactElement {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const scatterplotRef = useRef<Scatterplot | null>(null);
    const pointsRef = useRef<readonly CloudEntityPoint[]>([]);
    const hoveredIndexRef = useRef<number | null>(null);
    const previousHighlightedRef = useRef<EntityRef | null>(null);
    const pingCounterRef = useRef(0);
    const pingRef = useRef<Ping | null>(null);
    const onSelectRef = useRef(onSelect);
    const onFocusRef = useRef(onFocus);
    const onClearRef = useRef(onClear);
    const onHoverRef = useRef(onHover);
    onSelectRef.current = onSelect;
    onFocusRef.current = onFocus;
    onClearRef.current = onClear;
    onHoverRef.current = onHover;

    const [ping, setPing] = useState<Ping | null>(null);
    pingRef.current = ping;

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
            const entity = pointsRef.current[index]?.ref;
            const position = scatterplot.getScreenPosition(index);
            if (entity !== undefined && position !== undefined) {
                onHoverRef.current(entity, position);
            }
        });
        const pointOutSubscription = scatterplot.subscribe("pointOut", () => {
            hoveredIndexRef.current = null;
            onHoverRef.current(null, null);
        });
        const deselectSubscription = scatterplot.subscribe("deselect", () => {
            onClearRef.current();
        });
        const viewSubscription = scatterplot.subscribe("view", () => {
            const activePing = pingRef.current;
            if (activePing === null) {
                return;
            }
            const position = scatterplot.getScreenPosition(activePing.pointIndex);
            if (position !== undefined) {
                setPing({ ...activePing, position });
            }
        });

        function handleClick(): void {
            if (hoveredIndexRef.current === null) {
                onClearRef.current();
            }
        }

        function handleDoubleClick(): void {
            const index = hoveredIndexRef.current;
            const entity = index === null ? undefined : pointsRef.current[index]?.ref;
            if (entity !== undefined) {
                onFocusRef.current(entity);
            }
        }

        canvas.addEventListener("click", handleClick);
        canvas.addEventListener("dblclick", handleDoubleClick);

        return (): void => {
            canvas.removeEventListener("click", handleClick);
            canvas.removeEventListener("dblclick", handleDoubleClick);
            scatterplot.unsubscribe(selectSubscription);
            scatterplot.unsubscribe(pointOverSubscription);
            scatterplot.unsubscribe(pointOutSubscription);
            scatterplot.unsubscribe(deselectSubscription);
            scatterplot.unsubscribe(viewSubscription);
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
            if (!sameHighlight(highlighted, previousHighlightedRef.current)) {
                const position = scatterplot.getScreenPosition(highlightedIndex);
                if (position !== undefined) {
                    pingCounterRef.current += 1;
                    setPing({ key: pingCounterRef.current, pointIndex: highlightedIndex, position });
                }
            }
        } else {
            scatterplot.deselect({ preventEvent: true });
        }
        previousHighlightedRef.current = highlighted;
    }, [points, highlighted]);

    useEffect(() => {
        if (ping === null) {
            return undefined;
        }

        const timeout = setTimeout(() => {
            setPing(null);
        }, PING_LIFETIME_MS);
        return (): void => {
            clearTimeout(timeout);
        };
    }, [ping]);

    return (
        <div className="cloud-wrap">
            <div className="cloud-canvas" ref={containerRef} />
            {ping !== null && (
                <span key={ping.key} className="cloud-ping" style={{ left: ping.position[0], top: ping.position[1] }}>
                    <span className="cloud-ping-ring" />
                    <span className="cloud-ping-ring cloud-ping-ring-delayed" />
                </span>
            )}
            {points.length === 0 && (
                <div className="cloud-empty">
                    <h4>No cloud coordinates yet</h4>
                    <p>Run the embedding pipeline to populate this view with positions.</p>
                </div>
            )}
        </div>
    );
}
