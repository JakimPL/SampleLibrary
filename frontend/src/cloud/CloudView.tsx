import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import createScatterplot from "regl-scatterplot";

import { CATEGORY_ORDER, categoryColorProperty, categoryIndex } from "../samples/category";
import { labelColor, readLabelPaletteParameters } from "../theme/labelPalette";
import { readThemeColor } from "../theme/readThemeColor";
import { useThemeSignal } from "../theme/useThemeSignal";
import type { EntityRef } from "../workspace/selectionStore";
import { type CloudEntityPoint, normalizePoints } from "./geometry";
import { type PointColoring, SUBSTRATE_SLOT } from "./labelColoring";
import { MorphBand } from "./MorphBand";
import { MorphLink } from "./MorphLink";

type Scatterplot = ReturnType<typeof createScatterplot>;
type ScreenPosition = readonly [number, number];

const POINT_SIZE = 2.5;
const POINT_SIZE_SELECTED = 9;
const POINT_COLOR_PROPERTY = "--cloud-point";
const POINT_COLOR_FALLBACK = "#1b1f26";
const SELECTED_COLOR_PROPERTY = "--cloud-point-selected";
const SELECTED_COLOR_FALLBACK = "#a8690f";
const BACKGROUND_COLOR_PROPERTY = "--cloud-bg";
const BACKGROUND_COLOR_FALLBACK = "#f4f5f7";
const UNCATEGORIZED_CATEGORY = "uncategorized";
const UNCATEGORIZED_COLOR_PROPERTY = "--cloud-point-uncategorized";
const UNCATEGORIZED_COLOR_FALLBACK = "#d5d4ce";
const CATEGORICAL_COLOR_BY = "category";

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

// Most of a real library's samples match no category keyword, so drawing them as strongly as the
// classified ones buries the very structure the colors exist to show. They take a recessive tone of
// their own instead, reading as the substrate the classified points sit in.
function readCategoryPalette(): string[] {
    return CATEGORY_ORDER.map((category) =>
        category === UNCATEGORIZED_CATEGORY
            ? readThemeColor(UNCATEGORIZED_COLOR_PROPERTY, UNCATEGORIZED_COLOR_FALLBACK)
            : readThemeColor(categoryColorProperty(category), POINT_COLOR_FALLBACK),
    );
}

// The tags a person chose to paint sit on the same recessive ground the uncategorized points do,
// so the labeled samples stand out of a catalog that is mostly unlabeled.
function readLabelPalette(ranks: readonly number[]): string[] {
    const parameters = readLabelPaletteParameters();
    return [
        readThemeColor(UNCATEGORIZED_COLOR_PROPERTY, UNCATEGORIZED_COLOR_FALLBACK),
        ...ranks.map((rank) => labelColor(rank, parameters)),
    ];
}

interface DrawSpec {
    readonly positions: number[][];
    readonly categorized: boolean;
    readonly colorBy: typeof CATEGORICAL_COLOR_BY | null;
    readonly pointColor: string | string[];
}

/**
 * Builds both the point positions and the color configuration a draw call needs from one pass over
 * `points`, since the two must agree: a sample-cloud point always carries a `category` (worst case
 * "uncategorized"), so a batch where every point has one gets a `[x, y, slot]` triple and
 * regl-scatterplot's own categorical coloring (`colorBy: 'category'`, one `pointColor` entry per
 * slot) -- the slot being the point's `CATEGORY_ORDER` index, or under a label `coloring` the slot
 * its painted tag holds; a module-cloud point carries no category, so its batch stays a plain
 * `[x, y]` pair under the shell's single flat point color -- the two tabs share one scatterplot
 * instance (see `CloudPanel`), so this decides per draw call which of the two point kinds is on
 * screen.
 */
function buildDrawSpec(points: readonly CloudEntityPoint[], coloring: PointColoring): DrawSpec {
    const categorized = points.length > 0 && points.every((point) => point.category !== undefined);
    if (!categorized) {
        return {
            positions: points.map((point) => [point.x, point.y]),
            categorized,
            colorBy: null,
            pointColor: readThemeColor(POINT_COLOR_PROPERTY, POINT_COLOR_FALLBACK),
        };
    }
    if (coloring.kind === "label") {
        return {
            positions: points.map((point) => [
                point.x,
                point.y,
                coloring.slotByHash.get(point.ref.hash) ?? SUBSTRATE_SLOT,
            ]),
            categorized,
            colorBy: CATEGORICAL_COLOR_BY,
            pointColor: readLabelPalette(coloring.ranks),
        };
    }
    return {
        positions: points.map((point) => [point.x, point.y, categoryIndex(point.category ?? UNCATEGORIZED_CATEGORY)]),
        categorized,
        colorBy: CATEGORICAL_COLOR_BY,
        pointColor: readCategoryPalette(),
    };
}

// Kept in step with the ring animations' own total duration in styles.css (two staggered 1400ms
// rings, the second delayed by 300ms) so the marker element is dropped only once both have faded.
const PING_LIFETIME_MS = 1900;

/** A morph pair drawn over the cloud: its two ends by hash, and the weight its marker sits at. */
export interface CloudLink {
    readonly first: string;
    readonly second: string;
    readonly weight: number;
}

interface CloudViewProps {
    readonly points: readonly CloudEntityPoint[];
    readonly coloring: PointColoring;
    readonly highlighted: EntityRef | null;
    readonly onSelect: (entity: EntityRef) => void;
    readonly onFocus: (entity: EntityRef) => void;
    readonly onClear: () => void;
    readonly onHover: (entity: EntityRef | null, screenPosition: ScreenPosition | null) => void;
    readonly onCompare: (entity: EntityRef) => void;
    readonly onActivate: (entity: EntityRef) => void;
    readonly link: CloudLink | null;
    readonly onWeightChange: (weight: number) => void;
    readonly onWeightCommit: () => void;
    /** The sample a Shift-click would morph from, by hash, which the band follows the cursor from. */
    readonly anchor: string | null;
}

interface Ping {
    readonly key: number;
    readonly pointIndex: number;
    readonly position: ScreenPosition;
}

interface ScreenSegment {
    readonly first: ScreenPosition;
    readonly second: ScreenPosition;
}

function samePosition(a: ScreenPosition, b: ScreenPosition): boolean {
    return a[0] === b[0] && a[1] === b[1];
}

function sameSegment(a: ScreenSegment | null, b: ScreenSegment | null): boolean {
    return a === null || b === null ? a === b : samePosition(a.first, b.first) && samePosition(a.second, b.second);
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
    coloring: PointColoring,
): Promise<void> {
    const spec = buildDrawSpec(points, coloring);
    const runDraw = (): Promise<void> =>
        scatterplot
            .set({ colorBy: spec.colorBy, pointColor: spec.pointColor })
            .then(() => scatterplot.draw(spec.positions, spec.categorized ? { zDataType: "categorical" } : undefined));
    const next = chain.current.then(runDraw, runDraw);
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
 * effectively does. `isCanceled` reports true once the effect that started this call has been
 * cleaned up (its scatterplot destroyed, e.g. by an unmount racing the pending draw), so its result
 * goes unused.
 *
 * A queued draw can reach the front of `drawChain` only after its own effect's cleanup already
 * destroyed the scatterplot -- an unmount racing a still-pending, serialized-behind-another draw --
 * in which case regl-scatterplot rejects it outright rather than running. That rejection is exactly
 * as moot as any other canceled result, so it is treated the same way once `isCanceled` confirms
 * it was expected; a draw failing for any other reason still surfaces, since nothing else here knows
 * how to recover from it.
 */
async function applyPoints(
    scatterplot: Scatterplot,
    drawChain: DrawChain,
    points: readonly CloudEntityPoint[],
    coloring: PointColoring,
    highlighted: EntityRef | null,
    isCanceled: () => boolean,
): Promise<number> {
    try {
        await drawSerialized(scatterplot, drawChain, points, coloring);
    } catch (error) {
        if (isCanceled()) {
            return -1;
        }
        throw error;
    }
    if (isCanceled()) {
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
 * double-click behavior only deselects, so this view disables it (`deselectOnDblClick: false`)
 * and focuses the hovered point on a native double-click instead, looked up through the library's
 * continuous `pointOver`/`pointOut` hover tracking -- the same tracking a miss-click reads to tell
 * a hit from empty space, and that `onHover` reports upward for a caller-rendered detail popup.
 * Pressing Escape while the canvas has focus clears the highlight too, through the library's own
 * built-in `deselect` behavior. Whenever `highlighted` changes to a point present in this view (a
 * click elsewhere in the shell just located a sample or module here), a brief sonar-style ping
 * marks its screen position -- tracking the library's own `view` event so the ping stays pinned to
 * the point through any pan or zoom while it plays, rather than drifting off it. Selecting a point
 * this way also reports it through `onActivate` (a sample tab's caller uses this to start playback),
 * but skips its own ping for that one transition: the click that just selected it is already looking
 * straight at it, so the locate cue is reserved for a highlight arriving from somewhere else in the
 * shell. A Shift-click over a point reports it through `onCompare` alone: capture-phase listeners
 * take the press and the click before the library's own, so the point is neither selected nor
 * played, and the highlight that anchors a morph stays where it was. While Shift is held over the
 * canvas and `anchor` names a point in view, a band runs from that point to the cursor, snapping
 * to the point under it, so the pair a Shift-click would join is visible before it lands. When
 * `link` names two points in view, a dashed line joins them and its marker is the weight, kept
 * pinned through the library's `view` event the way the ping is and re-read when the container
 * resizes; the hover tracking pauses while the marker is dragged, since the library keeps
 * hit-testing beneath it.
 * Point, active-point,
 * and background colors are read from the theme's CSS custom properties at creation, and re-applied
 * through the library's own `set` whenever `useThemeSignal` reports the resolved theme could have
 * changed, mirroring how `useWaveformPlayer.ts` keeps wavesurfer's own canvas in step. Points draw
 * as circles carrying a background-colored outline, which keeps each one readable where a dense
 * region crowds many together. Points that carry a `category`
 * (every sample-cloud point does; a module-cloud point carries none) draw with regl-scatterplot's
 * own categorical coloring instead of the flat point color, one fixed hue per `SampleCategory` --
 * see `buildDrawSpec`, which both draw calls and the theme re-apply above route through so the two
 * stay in step regardless of which of this view's two entity kinds is currently on screen.
 */
export function CloudView({
    points: rawPoints,
    coloring,
    highlighted,
    onSelect,
    onFocus,
    onClear,
    onHover,
    onCompare,
    onActivate,
    link,
    onWeightChange,
    onWeightCommit,
    anchor,
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
    const coloringRef = useRef<PointColoring>(coloring);
    coloringRef.current = coloring;
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
    const linkRef = useRef<CloudLink | null>(link);
    linkRef.current = link;
    const onWeightChangeRef = useRef(onWeightChange);
    const onWeightCommitRef = useRef(onWeightCommit);
    onWeightChangeRef.current = onWeightChange;
    onWeightCommitRef.current = onWeightCommit;
    const linkDraggingRef = useRef(false);
    const anchorRef = useRef<string | null>(anchor);
    anchorRef.current = anchor;
    // Where the cursor last stood over the canvas, and whether Shift is down: the two facts the
    // band is drawn from, kept as refs so listeners on the canvas and the window share them.
    const cursorRef = useRef<ScreenPosition | null>(null);
    const shiftHeldRef = useRef(false);

    const [ping, setPing] = useState<Ping | null>(null);
    pingRef.current = ping;
    const [linkScreen, setLinkScreen] = useState<ScreenSegment | null>(null);
    const [band, setBand] = useState<ScreenSegment | null>(null);

    // Stable on `rawPoints` alone, not recomputed on every render, since it feeds the draw effect's
    // dependency array below -- an identity that changed on every render (including ones this view
    // causes itself, like a ping's own state update) would redraw the whole scatterplot far more
    // often than `rawPoints` actually changes.
    const points = useMemo(() => normalizePoints(rawPoints), [rawPoints]);
    pointsRef.current = points;
    const indexByHash = useMemo(
        () => new Map(points.map((point, index) => [point.ref.hash, index] as const)),
        [points],
    );
    const indexByHashRef = useRef(indexByHash);
    indexByHashRef.current = indexByHash;

    // Reads both ends' screen positions afresh; stable, so the mount effect's subscriptions and the
    // effects below share one function. The link goes unshown while either end is out of this
    // view (the other tab, a pair joined before the points arrived) or the first draw is pending.
    const repinLink = useCallback((): void => {
        const scatterplot = scatterplotRef.current;
        const currentLink = linkRef.current;
        if (scatterplot === null || currentLink === null || !pointsDrawnRef.current) {
            setLinkScreen(null);
            return;
        }
        const firstIndex = indexByHashRef.current.get(currentLink.first);
        const secondIndex = indexByHashRef.current.get(currentLink.second);
        const first = firstIndex === undefined ? undefined : scatterplot.getScreenPosition(firstIndex);
        const second = secondIndex === undefined ? undefined : scatterplot.getScreenPosition(secondIndex);
        if (first === undefined || second === undefined) {
            setLinkScreen(null);
            return;
        }
        const next: ScreenSegment = { first, second };
        setLinkScreen((current) => (sameSegment(current, next) ? current : next));
    }, []);

    // The band from the anchor to the cursor while Shift is held, its far end snapped to the point
    // under the cursor; refs alone, so the mount effect's listeners and the effects below share it.
    const repinBand = useCallback((): void => {
        const scatterplot = scatterplotRef.current;
        const anchorHash = anchorRef.current;
        const cursor = cursorRef.current;
        if (
            scatterplot === null ||
            anchorHash === null ||
            cursor === null ||
            !shiftHeldRef.current ||
            !pointsDrawnRef.current
        ) {
            setBand(null);
            return;
        }
        const anchorIndex = indexByHashRef.current.get(anchorHash);
        const anchorPosition = anchorIndex === undefined ? undefined : scatterplot.getScreenPosition(anchorIndex);
        if (anchorPosition === undefined) {
            setBand(null);
            return;
        }
        const hoveredIndex = hoveredIndexRef.current;
        const hoveredPosition =
            hoveredIndex === null || hoveredIndex === anchorIndex
                ? undefined
                : scatterplot.getScreenPosition(hoveredIndex);
        const next: ScreenSegment = { first: anchorPosition, second: hoveredPosition ?? cursor };
        setBand((current) => (sameSegment(current, next) ? current : next));
    }, []);

    const themeSignal = useThemeSignal();

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
        });
        scatterplotRef.current = scatterplot;
        pointsDrawnRef.current = false;
        drawChainRef.current = Promise.resolve();
        let canceled = false;
        void applyPoints(
            scatterplot,
            drawChainRef,
            pointsRef.current,
            coloringRef.current,
            highlighted,
            () => canceled,
        ).then(() => {
            if (!canceled) {
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
            if (linkDraggingRef.current) {
                return;
            }
            hoveredIndexRef.current = index;
            const entity = pointsRef.current[index]?.ref;
            const position = pointsDrawnRef.current ? scatterplot.getScreenPosition(index) : undefined;
            if (entity !== undefined && position !== undefined) {
                onHoverRef.current(entity, position);
            }
            repinBand();
        });
        const pointOutSubscription = scatterplot.subscribe("pointOut", () => {
            hoveredIndexRef.current = null;
            onHoverRef.current(null, null);
            repinBand();
        });
        const deselectSubscription = scatterplot.subscribe("deselect", () => {
            onClearRef.current();
        });
        const viewSubscription = scatterplot.subscribe("view", () => {
            repinLink();
            repinBand();
            const activePing = pingRef.current;
            if (activePing === null || !pointsDrawnRef.current) {
                return;
            }
            const position = scatterplot.getScreenPosition(activePing.pointIndex);
            if (position !== undefined) {
                setPing({ ...activePing, position });
            }
        });

        // Taken in the capture phase, before the library's own listeners on this same canvas: a
        // Shift press over a point would otherwise start its lasso, whose release deselects the
        // point already highlighted, and the click would select and so play the point pressed.
        function handleShiftPress(event: MouseEvent): void {
            if (event.shiftKey && hoveredIndexRef.current !== null) {
                event.stopImmediatePropagation();
            }
        }

        function handleShiftClick(event: MouseEvent): void {
            const index = hoveredIndexRef.current;
            const entity = index === null ? undefined : pointsRef.current[index]?.ref;
            if (!event.shiftKey || entity === undefined) {
                return;
            }
            event.stopImmediatePropagation();
            onCompareRef.current(entity);
        }

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

        function handleMouseMove(event: MouseEvent): void {
            const bounds = canvas.getBoundingClientRect();
            cursorRef.current = [event.clientX - bounds.left, event.clientY - bounds.top];
            shiftHeldRef.current = event.shiftKey;
            repinBand();
        }

        function handleMouseLeave(): void {
            cursorRef.current = null;
            repinBand();
        }

        // Read on the window, so Shift pressed or released while the cursor rests over the canvas
        // shows or drops the band without a move.
        function handleShiftKey(event: KeyboardEvent): void {
            if (event.key === "Shift") {
                shiftHeldRef.current = event.type === "keydown";
                repinBand();
            }
        }

        canvas.addEventListener("mousedown", handleShiftPress, { capture: true });
        canvas.addEventListener("click", handleShiftClick, { capture: true });
        canvas.addEventListener("click", handleClick);
        canvas.addEventListener("dblclick", handleDoubleClick);
        canvas.addEventListener("mousemove", handleMouseMove);
        canvas.addEventListener("mouseleave", handleMouseLeave);
        window.addEventListener("keydown", handleShiftKey);
        window.addEventListener("keyup", handleShiftKey);

        return (): void => {
            canceled = true;
            canvas.removeEventListener("mousedown", handleShiftPress, { capture: true });
            canvas.removeEventListener("click", handleShiftClick, { capture: true });
            canvas.removeEventListener("click", handleClick);
            canvas.removeEventListener("dblclick", handleDoubleClick);
            canvas.removeEventListener("mousemove", handleMouseMove);
            canvas.removeEventListener("mouseleave", handleMouseLeave);
            window.removeEventListener("keydown", handleShiftKey);
            window.removeEventListener("keyup", handleShiftKey);
            scatterplot.unsubscribe(selectSubscription);
            scatterplot.unsubscribe(pointOverSubscription);
            scatterplot.unsubscribe(pointOutSubscription);
            scatterplot.unsubscribe(deselectSubscription);
            scatterplot.unsubscribe(viewSubscription);
            scatterplot.destroy();
            scatterplotRef.current = null;
            canvas.remove();
        };
        // Created once per mount: point and highlight updates flow through the effect below, and a
        // theme switch restyles the live instance, so neither rebuilds the WebGL context.
        // highlighted is deliberately left out: this effect only needs its value at creation, and
        // reading it fresh here would otherwise force a recreation on every select.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        const scatterplot = scatterplotRef.current;
        if (scatterplot === null) {
            return undefined;
        }

        // Canceled if a newer call to this effect (points or highlighted changing again before
        // this draw resolves) supersedes this one -- otherwise a slow, stale draw could still land
        // its ping, or overwrite `previousHighlightedRef` with an already-outdated value, after a
        // newer run already has. The draw itself still queues behind the mount effect's own initial
        // draw (or any other run's) through `drawChainRef` regardless of this cancellation, since a
        // canceled run's `draw` call was already issued and the scatterplot has no way to retract it.
        let canceled = false;
        void applyPoints(scatterplot, drawChainRef, points, coloring, highlighted, () => canceled).then(
            (highlightedIndex) => {
                if (canceled) {
                    return;
                }

                pointsDrawnRef.current = true;
                repinLink();
                if (highlightedIndex >= 0 && !sameHighlight(highlighted, previousHighlightedRef.current)) {
                    const position = scatterplot.getScreenPosition(highlightedIndex);
                    if (position !== undefined) {
                        pingCounterRef.current += 1;
                        setPing({ key: pingCounterRef.current, pointIndex: highlightedIndex, position });
                    }
                }
                previousHighlightedRef.current = highlighted;
            },
        );
        return (): void => {
            canceled = true;
        };
    }, [points, coloring, highlighted, repinLink]);

    useEffect(() => {
        repinLink();
    }, [link, repinLink]);

    useEffect(() => {
        repinBand();
    }, [anchor, repinBand]);

    useEffect(() => {
        const container = containerRef.current;
        if (container === null) {
            return undefined;
        }
        const observer = new ResizeObserver(() => {
            repinLink();
        });
        observer.observe(container);
        return (): void => {
            observer.disconnect();
        };
    }, [repinLink]);

    useEffect(() => {
        // Redundantly re-applies the colors the mount effect above just set on the first render.
        // pointColor/colorBy specifically follow the currently-drawn points' own categorization
        // (see buildDrawSpec) rather than always falling back to the flat point color, so a live
        // theme switch while viewing the categorized Samples tab keeps every category's own color
        // instead of collapsing them all back to one.
        const { pointColorActive, backgroundColor } = readCloudColors();
        const spec = buildDrawSpec(pointsRef.current, coloringRef.current);
        void scatterplotRef.current?.set({
            pointColorActive,
            backgroundColor,
            colorBy: spec.colorBy,
            pointColor: spec.pointColor,
        });
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
            {band !== null && <MorphBand anchor={band.first} cursor={band.second} />}
            {link !== null && linkScreen !== null && (
                <MorphLink
                    first={linkScreen.first}
                    second={linkScreen.second}
                    weight={link.weight}
                    onWeightChange={(weight) => {
                        onWeightChangeRef.current(weight);
                    }}
                    onWeightCommit={() => {
                        onWeightCommitRef.current();
                    }}
                    onDragChange={(dragging) => {
                        linkDraggingRef.current = dragging;
                    }}
                />
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
