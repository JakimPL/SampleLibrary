import type { ReactElement } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import createScatterplot from "regl-scatterplot";

import { readThemeColor } from "../theme/readThemeColor";
import { useThemeSignal } from "../theme/useThemeSignal";
import type { EntityRef } from "../workspace/selectionStore";
import { type CloudEntityPoint, normalizePoints } from "./geometry";

type Scatterplot = ReturnType<typeof createScatterplot>;
type ScreenPosition = readonly [number, number];

const POINT_SIZE = 4;
const POINT_SIZE_SELECTED = 9;
const POINT_COLOR_PROPERTY = "--cloud-point";
const POINT_COLOR_FALLBACK = "#1b1f26";
const SELECTED_COLOR_PROPERTY = "--cloud-point-selected";
const SELECTED_COLOR_FALLBACK = "#a8690f";
const BACKGROUND_COLOR_PROPERTY = "--cloud-bg";
const BACKGROUND_COLOR_FALLBACK = "#f4f5f7";
const POINT_SHAPE_PROPERTY = "--cloud-point-shape";
const SQUARE_POINT_SHAPE_VALUE = "square";

interface CloudColors {
    readonly pointColor: string;
    readonly pointColorActive: string;
    readonly backgroundColor: string;
}

function readCloudColors(): CloudColors {
    return {
        pointColor: readThemeColor(POINT_COLOR_PROPERTY, POINT_COLOR_FALLBACK),
        pointColorActive: readThemeColor(SELECTED_COLOR_PROPERTY, SELECTED_COLOR_FALLBACK),
        backgroundColor: readThemeColor(BACKGROUND_COLOR_PROPERTY, BACKGROUND_COLOR_FALLBACK),
    };
}

// regl-scatterplot compiles its point shape into the WebGL shader at creation and has no setter
// for it afterwards (unlike color, which `.set()` updates live), so picking up a live theme switch
// between circle and square points means recreating the whole scatterplot rather than restyling it.
function readRenderPointsAsSquares(): boolean {
    return readThemeColor(POINT_SHAPE_PROPERTY, "") === SQUARE_POINT_SHAPE_VALUE;
}

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
    readonly onCompare: (entity: EntityRef) => void;
    readonly onActivate: (entity: EntityRef) => void;
}

interface Ping {
    readonly key: number;
    readonly pointIndex: number;
    readonly position: ScreenPosition;
}

function sameEntity(a: EntityRef, b: EntityRef): boolean {
    return a.kind === b.kind && a.hash === b.hash;
}

function sameHighlight(a: EntityRef | null, b: EntityRef | null): boolean {
    return a === null || b === null ? a === b : sameEntity(a, b);
}

interface DrawChain {
    current: Promise<void>;
}

/**
 * Runs `scatterplot.draw` through a per-instance chain rather than calling it directly, so a draw
 * requested while a previous one is still in flight waits its turn instead of firing alongside it.
 * regl-scatterplot has no queue of its own: a `draw` call made before the previous one settles
 * rejects outright with "Ignoring draw call...", and on this codebase's own reproduction, the call
 * that lost that race left the instance permanently unable to draw again (its `isDrawing` flag has
 * no path back to `false` once the draw it belonged to is abandoned this way). `points`/`highlighted`
 * can each change again before an in-progress draw resolves -- a second effect run superseding the
 * first, or the mount effect's own initial draw overlapping an update that arrives just after -- so
 * this chain is what keeps every such request queued rather than racing the live scatterplot.
 */
function drawSerialized(
    scatterplot: Scatterplot,
    chain: DrawChain,
    points: readonly CloudEntityPoint[],
): Promise<void> {
    const positions: number[][] = points.map((point) => [point.x, point.y]);
    const next = chain.current.then(
        () => scatterplot.draw(positions),
        () => scatterplot.draw(positions),
    );
    chain.current = next.then(
        () => undefined,
        () => undefined,
    );
    return next;
}

/**
 * Draws the current points and applies whichever one (if any) is highlighted -- shared by the
 * mount effect, which needs this once right after a shape-driven recreation, and the effect that
 * tracks `points`/`highlighted` changes on an already-created scatterplot. Awaits the (serialized)
 * draw before touching selection: regl-scatterplot throws "Points have not been drawn" from
 * `getScreenPosition` (and a caller reading it right after `select` hits the same unset state) if
 * it's called before a first `draw` resolves, which a fresh scatterplot -- still compiling its
 * WebGL shaders -- does not do synchronously the way an already-drawn one redrawing existing points
 * effectively does. `isCancelled` reports true once the effect that started this call has been
 * cleaned up (its scatterplot destroyed, e.g. by an unmount racing the pending draw), so its result
 * goes unused.
 *
 * A queued draw can reach the front of `drawChain` only after its own effect's cleanup already
 * destroyed the scatterplot -- an unmount racing a still-pending, serialized-behind-another draw --
 * in which case regl-scatterplot rejects it outright rather than running. That rejection is exactly
 * as moot as any other cancelled result, so it is treated the same way once `isCancelled` confirms
 * it was expected; a draw failing for any other reason still surfaces, since nothing else here knows
 * how to recover from it.
 */
async function applyPoints(
    scatterplot: Scatterplot,
    drawChain: DrawChain,
    points: readonly CloudEntityPoint[],
    highlighted: EntityRef | null,
    isCancelled: () => boolean,
): Promise<number> {
    try {
        await drawSerialized(scatterplot, drawChain, points);
    } catch (error) {
        if (isCancelled()) {
            return -1;
        }
        throw error;
    }
    if (isCancelled()) {
        return -1;
    }

    const highlightedIndex =
        highlighted === null ? -1 : points.findIndex((point) => sameEntity(point.ref, highlighted));
    if (highlightedIndex >= 0) {
        scatterplot.select([highlightedIndex], { preventEvent: true });
    } else {
        scatterplot.deselect({ preventEvent: true });
    }
    return highlightedIndex;
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
 * the point through any pan or zoom while it plays, rather than drifting off it. Selecting a point
 * this way also reports it through `onActivate` (a sample tab's caller uses this to start playback),
 * but skips its own ping for that one transition: the click that just selected it is already looking
 * straight at it, so the locate cue is reserved for a highlight arriving from somewhere else in the
 * shell. A Shift-click over a point reports it through `onCompare` alongside regl-scatterplot's own
 * unavoidable normal select -- the library has no way to suppress its own hit-testing from our own
 * listener, so `onActivate` fires for a Shift-click too. Point, active-point,
 * and background colors are read from the theme's CSS custom properties at creation, and re-applied
 * through the library's own `set` whenever `useThemeSignal` reports the resolved theme could have
 * changed, mirroring how `useWaveformPlayer.ts` keeps wavesurfer's own canvas in step. Point shape
 * (circle or square) is read the same way, but the library compiles it into the WebGL shader at
 * creation with no live setter, so a theme switch that flips it recreates the whole scatterplot
 * instead -- the one visual this view cannot just restyle in place.
 */
export function CloudView({
    points: rawPoints,
    highlighted,
    onSelect,
    onFocus,
    onClear,
    onHover,
    onCompare,
    onActivate,
}: CloudViewProps): ReactElement {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const scatterplotRef = useRef<Scatterplot | null>(null);
    // Serializes every `draw` call against the current scatterplot instance -- see `drawSerialized`.
    // Reset on each (re)creation so a chain left over from a just-destroyed instance is abandoned
    // rather than carried into the new one.
    const drawChainRef = useRef<Promise<void>>(Promise.resolve());
    // Tracks whether the current scatterplot's first `draw` has resolved -- `getScreenPosition`
    // throws until it has, so the hover and ping-repositioning subscriptions check this before
    // calling it rather than risk that throw crashing an unrelated passive-effect commit.
    const pointsDrawnRef = useRef(false);
    const pointsRef = useRef<readonly CloudEntityPoint[]>([]);
    const hoveredIndexRef = useRef<number | null>(null);
    const previousHighlightedRef = useRef<EntityRef | null>(null);
    const pingCounterRef = useRef(0);
    const pingRef = useRef<Ping | null>(null);
    const onSelectRef = useRef(onSelect);
    const onFocusRef = useRef(onFocus);
    const onClearRef = useRef(onClear);
    const onHoverRef = useRef(onHover);
    const onCompareRef = useRef(onCompare);
    const onActivateRef = useRef(onActivate);
    onSelectRef.current = onSelect;
    onFocusRef.current = onFocus;
    onClearRef.current = onClear;
    onHoverRef.current = onHover;
    onCompareRef.current = onCompare;
    onActivateRef.current = onActivate;

    const [ping, setPing] = useState<Ping | null>(null);
    pingRef.current = ping;

    // Stable on `rawPoints` alone, not recomputed on every render, since it feeds the draw effect's
    // dependency array below -- an identity that changed on every render (including ones this view
    // causes itself, like a ping's own state update) would redraw the whole scatterplot far more
    // often than `rawPoints` actually changes.
    const points = useMemo(() => normalizePoints(rawPoints), [rawPoints]);
    pointsRef.current = points;

    const themeSignal = useThemeSignal();
    const renderPointsAsSquares = readRenderPointsAsSquares();

    useEffect(() => {
        const container = containerRef.current;
        if (container === null) {
            return undefined;
        }

        const canvas = document.createElement("canvas");
        container.append(canvas);

        const scatterplot = createScatterplot({
            canvas,
            ...readCloudColors(),
            pointSize: POINT_SIZE,
            pointSizeSelected: POINT_SIZE_SELECTED,
            deselectOnDblClick: false,
            renderPointsAsSquares,
        });
        scatterplotRef.current = scatterplot;
        pointsDrawnRef.current = false;
        drawChainRef.current = Promise.resolve();
        let cancelled = false;
        void applyPoints(scatterplot, drawChainRef, pointsRef.current, highlighted, () => cancelled).then(() => {
            if (!cancelled) {
                pointsDrawnRef.current = true;
            }
        });

        const selectSubscription = scatterplot.subscribe("select", ({ points: selectedIndices }) => {
            const index = selectedIndices[0];
            const entity = index === undefined ? undefined : pointsRef.current[index]?.ref;
            if (entity !== undefined) {
                // Recorded before `onSelect` even runs: `highlighted` catching up to this same
                // entity is this click's own doing, not a locate request from elsewhere, so the
                // points/highlighted effect's ping guard (comparing against this same ref) skips it.
                previousHighlightedRef.current = entity;
                onSelectRef.current(entity);
                onActivateRef.current(entity);
            }
        });
        const pointOverSubscription = scatterplot.subscribe("pointOver", (index) => {
            hoveredIndexRef.current = index;
            const entity = pointsRef.current[index]?.ref;
            const position = pointsDrawnRef.current ? scatterplot.getScreenPosition(index) : undefined;
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
            if (activePing === null || !pointsDrawnRef.current) {
                return;
            }
            const position = scatterplot.getScreenPosition(activePing.pointIndex);
            if (position !== undefined) {
                setPing({ ...activePing, position });
            }
        });

        function handleClick(event: MouseEvent): void {
            const index = hoveredIndexRef.current;
            if (index === null) {
                onClearRef.current();
                return;
            }
            if (event.shiftKey) {
                const entity = pointsRef.current[index]?.ref;
                if (entity !== undefined) {
                    onCompareRef.current(entity);
                }
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
            cancelled = true;
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
        // Recreated only when the point shape flips (see readRenderPointsAsSquares above); point and
        // highlight updates otherwise flow through the effect below rather than recreating the whole
        // WebGL context.
        // highlighted is deliberately left out: this effect only needs its value at the moment of
        // (re)creation, and reading it fresh here would otherwise force a recreation on every select.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [renderPointsAsSquares]);

    useEffect(() => {
        const scatterplot = scatterplotRef.current;
        if (scatterplot === null) {
            return undefined;
        }

        // Cancelled if a newer call to this effect (points or highlighted changing again before
        // this draw resolves) supersedes this one -- otherwise a slow, stale draw could still land
        // its ping, or overwrite `previousHighlightedRef` with an already-outdated value, after a
        // newer run already has. The draw itself still queues behind the mount effect's own initial
        // draw (or any other run's) through `drawChainRef` regardless of this cancellation, since a
        // cancelled run's `draw` call was already issued and the scatterplot has no way to retract it.
        let cancelled = false;
        void applyPoints(scatterplot, drawChainRef, points, highlighted, () => cancelled).then((highlightedIndex) => {
            if (cancelled) {
                return;
            }

            pointsDrawnRef.current = true;
            if (highlightedIndex >= 0 && !sameHighlight(highlighted, previousHighlightedRef.current)) {
                const position = scatterplot.getScreenPosition(highlightedIndex);
                if (position !== undefined) {
                    pingCounterRef.current += 1;
                    setPing({ key: pingCounterRef.current, pointIndex: highlightedIndex, position });
                }
            }
            previousHighlightedRef.current = highlighted;
        });
        return (): void => {
            cancelled = true;
        };
    }, [points, highlighted]);

    useEffect(() => {
        // Redundantly re-applies the colors the mount effect above just set on the first render.
        void scatterplotRef.current?.set(readCloudColors());
    }, [themeSignal.preference, themeSignal.systemVersion]);

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
