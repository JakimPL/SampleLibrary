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
const LEFT_BUTTON = 0;
const RIGHT_BUTTON = 2;
// How far a press may travel and still read as a click rather than the end of a pan.
const CLICK_DRAG_TOLERANCE_PX = 4;

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

/**
 * One color per category slot. Uncategorized samples, most of a real library, take a recessive tone so the
 * classified structure stands out.
 */
function readCategoryPalette(): string[] {
    return CATEGORY_ORDER.map((category) =>
        category === UNCATEGORIZED_CATEGORY
            ? readThemeColor(UNCATEGORIZED_COLOR_PROPERTY, UNCATEGORIZED_COLOR_FALLBACK)
            : readThemeColor(categoryColorProperty(category), POINT_COLOR_FALLBACK),
    );
}

/**
 * The painted tags' colors after the recessive substrate slot, so labeled samples stand out of a mostly
 * unlabeled catalog.
 */
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

// Matches the two ping rings in styles.css: 1400ms each, the second delayed by 300ms.
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
    readonly onJoin: (first: EntityRef, second: EntityRef) => void;
    readonly onActivate: (entity: EntityRef) => void;
    readonly link: CloudLink | null;
    readonly onWeightChange: (weight: number) => void;
    readonly onWeightCommit: () => void;
    /** The sample, by hash, a right-drag runs from when the press lands on empty space. */
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

interface DragOrigin {
    readonly index: number;
    readonly pressedOnPoint: boolean;
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

    return selectHighlighted(scatterplot, points, highlighted);
}

/** Selects the highlighted point within the drawn scatterplot, or deselects when it names none here, and reports its index. */
function selectHighlighted(
    scatterplot: Scatterplot,
    points: readonly CloudEntityPoint[],
    highlighted: EntityRef | null,
): number {
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
 * shell. The right button is the pairing gesture, which the library leaves alone (it pans, selects
 * and lassos on the left button only), so the browser's menu is the one thing kept off the canvas:
 * a right-drag from one point to another reports both through `onJoin`, and a right-click on a
 * point, pressed and released in place, reports that point through `onCompare` for the caller to
 * join from its own anchor. While the button is held, a band runs from the point pressed, or from
 * `anchor` when the press landed on empty space, to the cursor, snapping to the point under it,
 * so the pair a release would join is visible before it lands. When
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
    onJoin,
    onActivate,
    link,
    onWeightChange,
    onWeightCommit,
    anchor,
}: CloudViewProps): ReactElement {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const scatterplotRef = useRef<Scatterplot | null>(null);
    const drawChainRef = useRef<Promise<void>>(Promise.resolve());
    // regl-scatterplot's `getScreenPosition` throws until the first `draw` resolves.
    const pointsDrawnRef = useRef(false);
    const pointsRef = useRef<readonly CloudEntityPoint[]>([]);
    const coloringRef = useRef<PointColoring>(coloring);
    coloringRef.current = coloring;
    const hoveredIndexRef = useRef<number | null>(null);
    const previousHighlightedRef = useRef<EntityRef | null>(null);
    const highlightedRef = useRef<EntityRef | null>(highlighted);
    highlightedRef.current = highlighted;
    const pressPositionRef = useRef<ScreenPosition | null>(null);
    const pingCounterRef = useRef(0);
    const pingRef = useRef<Ping | null>(null);
    const onSelectRef = useRef(onSelect);
    const onFocusRef = useRef(onFocus);
    const onClearRef = useRef(onClear);
    const onHoverRef = useRef(onHover);
    const onCompareRef = useRef(onCompare);
    const onJoinRef = useRef(onJoin);
    const onActivateRef = useRef(onActivate);
    onSelectRef.current = onSelect;
    onFocusRef.current = onFocus;
    onClearRef.current = onClear;
    onHoverRef.current = onHover;
    onCompareRef.current = onCompare;
    onJoinRef.current = onJoin;
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
    const dragOriginRef = useRef<DragOrigin | null>(null);
    const cursorRef = useRef<ScreenPosition | null>(null);

    const [ping, setPing] = useState<Ping | null>(null);
    pingRef.current = ping;
    const [linkScreen, setLinkScreen] = useState<ScreenSegment | null>(null);
    const [band, setBand] = useState<ScreenSegment | null>(null);

    const points = useMemo(() => normalizePoints(rawPoints), [rawPoints]);
    pointsRef.current = points;
    const indexByHash = useMemo(
        () => new Map(points.map((point, index) => [point.ref.hash, index] as const)),
        [points],
    );
    const indexByHashRef = useRef(indexByHash);
    indexByHashRef.current = indexByHash;

    /**
     * Pins the link to both ends' screen positions, hiding it while an end is outside this view or the first
     * draw is pending.
     */
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

    const repinBand = useCallback((): void => {
        const scatterplot = scatterplotRef.current;
        const origin = dragOriginRef.current;
        const cursor = cursorRef.current;
        if (scatterplot === null || origin === null || cursor === null || !pointsDrawnRef.current) {
            setBand(null);
            return;
        }
        const originPosition = scatterplot.getScreenPosition(origin.index);
        if (originPosition === undefined) {
            setBand(null);
            return;
        }
        const hoveredIndex = hoveredIndexRef.current;
        const hoveredPosition =
            hoveredIndex === null || hoveredIndex === origin.index
                ? undefined
                : scatterplot.getScreenPosition(hoveredIndex);
        const next: ScreenSegment = { first: originPosition, second: hoveredPosition ?? cursor };
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
                // Set before `onSelect`, so the ping guard reads the highlight that follows as this click's own.
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

        function cursorOf(event: MouseEvent): ScreenPosition {
            const bounds = canvas.getBoundingClientRect();
            return [event.clientX - bounds.left, event.clientY - bounds.top];
        }

        function handlePress(event: MouseEvent): void {
            if (event.button === LEFT_BUTTON) {
                pressPositionRef.current = cursorOf(event);
            }
            handleRightPress(event);
        }

        function handleRightPress(event: MouseEvent): void {
            if (event.button !== RIGHT_BUTTON) {
                return;
            }
            const hoveredIndex = hoveredIndexRef.current;
            const anchorHash = anchorRef.current;
            const anchorIndex = anchorHash === null ? undefined : indexByHashRef.current.get(anchorHash);
            const index = hoveredIndex ?? anchorIndex;
            if (index === undefined) {
                return;
            }
            dragOriginRef.current = { index, pressedOnPoint: hoveredIndex !== null };
            cursorRef.current = cursorOf(event);
            repinBand();
        }

        function handleRightRelease(event: MouseEvent): void {
            const origin = dragOriginRef.current;
            if (event.button !== RIGHT_BUTTON || origin === null) {
                return;
            }
            dragOriginRef.current = null;
            repinBand();
            const targetIndex = hoveredIndexRef.current;
            const first = pointsRef.current[origin.index]?.ref;
            const second = targetIndex === null ? undefined : pointsRef.current[targetIndex]?.ref;
            if (first === undefined || second === undefined) {
                return;
            }
            if (targetIndex !== origin.index) {
                onJoinRef.current(first, second);
            } else if (origin.pressedOnPoint) {
                onCompareRef.current(second);
            }
        }

        function handleContextMenu(event: MouseEvent): void {
            event.preventDefault();
        }

        function handleClick(event: MouseEvent): void {
            const pressed = pressPositionRef.current;
            pressPositionRef.current = null;
            if (pressed !== null) {
                const [x, y] = cursorOf(event);
                if (Math.hypot(x - pressed[0], y - pressed[1]) > CLICK_DRAG_TOLERANCE_PX) {
                    return;
                }
            }
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
            cursorRef.current = cursorOf(event);
            repinBand();
        }

        function handleMouseLeave(): void {
            cursorRef.current = null;
            repinBand();
        }

        canvas.addEventListener("mousedown", handlePress);
        canvas.addEventListener("contextmenu", handleContextMenu);
        canvas.addEventListener("click", handleClick);
        canvas.addEventListener("dblclick", handleDoubleClick);
        canvas.addEventListener("mousemove", handleMouseMove);
        canvas.addEventListener("mouseleave", handleMouseLeave);
        window.addEventListener("mouseup", handleRightRelease);

        return (): void => {
            canceled = true;
            canvas.removeEventListener("mousedown", handlePress);
            canvas.removeEventListener("contextmenu", handleContextMenu);
            canvas.removeEventListener("click", handleClick);
            canvas.removeEventListener("dblclick", handleDoubleClick);
            canvas.removeEventListener("mousemove", handleMouseMove);
            canvas.removeEventListener("mouseleave", handleMouseLeave);
            window.removeEventListener("mouseup", handleRightRelease);
            scatterplot.unsubscribe(selectSubscription);
            scatterplot.unsubscribe(pointOverSubscription);
            scatterplot.unsubscribe(pointOutSubscription);
            scatterplot.unsubscribe(deselectSubscription);
            scatterplot.unsubscribe(viewSubscription);
            scatterplot.destroy();
            scatterplotRef.current = null;
            canvas.remove();
        };
        // Created once per mount, reading `highlighted` at creation; the effects below update the live instance.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    /** Pings a highlight that arrived from elsewhere in the shell, once per change of highlight. */
    const pingNewHighlight = useCallback((scatterplot: Scatterplot, highlightedIndex: number): void => {
        const current = highlightedRef.current;
        if (highlightedIndex >= 0 && !sameHighlight(current, previousHighlightedRef.current)) {
            const position = scatterplot.getScreenPosition(highlightedIndex);
            if (position !== undefined) {
                pingCounterRef.current += 1;
                setPing({ key: pingCounterRef.current, pointIndex: highlightedIndex, position });
            }
        }
        previousHighlightedRef.current = current;
    }, []);

    useEffect(() => {
        const scatterplot = scatterplotRef.current;
        if (scatterplot === null) {
            return undefined;
        }

        let canceled = false;
        void applyPoints(scatterplot, drawChainRef, points, coloring, highlightedRef.current, () => canceled).then(
            (highlightedIndex) => {
                if (canceled) {
                    return;
                }

                pointsDrawnRef.current = true;
                repinLink();
                pingNewHighlight(scatterplot, highlightedIndex);
            },
        );
        return (): void => {
            canceled = true;
        };
    }, [points, coloring, repinLink, pingNewHighlight]);

    // A highlight moving from one point to another selects it among the points already drawn, so the
    // cloud's hundred thousand points are drawn again only when they themselves change.
    useEffect(() => {
        const scatterplot = scatterplotRef.current;
        if (scatterplot === null) {
            return undefined;
        }

        let canceled = false;
        void drawChainRef.current.then(() => {
            if (canceled || !pointsDrawnRef.current) {
                return;
            }
            pingNewHighlight(scatterplot, selectHighlighted(scatterplot, pointsRef.current, highlighted));
        });
        return (): void => {
            canceled = true;
        };
    }, [highlighted, pingNewHighlight]);

    useEffect(() => {
        repinLink();
    }, [link, repinLink]);

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
            {band !== null && <MorphBand origin={band.first} cursor={band.second} />}
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
