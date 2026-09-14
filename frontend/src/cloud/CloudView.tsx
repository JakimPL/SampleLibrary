import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import createScatterplot from "regl-scatterplot";

import type { EntityRef } from "../workspace/selectionStore";
import { CloudMarkers, type MarkerPositions, NO_MARKERS, sameMarkers } from "./CloudMarkers";
import { type CloudRenderSettings, useCloudRenderSettings } from "./cloudRenderSettings";
import { type CloudEntityPoint, normalizePoints } from "./geometry";
import type { PointColoring } from "./labelColoring";
import type { MarkerAppearance } from "./markerGeometry";
import { MorphBand } from "./MorphBand";
import { MorphLink } from "./MorphLink";
import { drawOrder, paletteColors, type PointSlots, slotPoints, slotValues } from "./pointPalette";

type Scatterplot = ReturnType<typeof createScatterplot>;
type ScatterplotProperties = Parameters<Scatterplot["set"]>[0];
type ScatterplotColor = NonNullable<ScatterplotProperties["pointColorActive"]>;
type ScreenPosition = readonly [number, number];

const CATEGORICAL_ENCODING = "category";
const CATEGORICAL_DATA = "categorical";
const SQUARE_SHAPE = "square";
const CAMERA_VIEW_PROPERTY = "cameraView";
const LEFT_BUTTON = 0;
const RIGHT_BUTTON = 2;
// How far a press may travel and still read as a click rather than the end of a pan.
const CLICK_DRAG_TOLERANCE_PX = 4;

/**
 * One copy of `color` per palette slot. A categorical point keeps its active and hover colors apart
 * from its own hue only when those come as one color per slot; a single color makes the scatterplot
 * paint an active or hovered point in its own hue.
 */
function perSlotColor(color: string, slotCount: number): ScatterplotColor {
    // regl-scatterplot reads an array of per-slot colors here at runtime, while its typings declare a single color.
    return Array.from({ length: slotCount }, () => color) as unknown as ScatterplotColor;
}

/**
 * How the scatterplot draws its points under the current theme and coloring: the properties it is
 * created with and that `set` re-applies. A categorized batch paints each slot in its own color,
 * size and opacity, the substrate's slot finer and fainter than the rest; the module cloud paints in
 * one flat color. Square points snap to the device's pixel grid, which is what keeps them crisp.
 */
function pointAppearance(
    slotting: PointSlots | null,
    coloring: PointColoring,
    settings: CloudRenderSettings,
): ScatterplotProperties {
    const { point, colors } = settings;
    const style: ScatterplotProperties = {
        backgroundColor: colors.background,
        pointSizeSelected: point.selectedExtraSizePx,
        pointOutlineWidth: point.outlineWidthPx,
        pointScaleMode: point.scaleMode,
        pixelAligned: point.shape === SQUARE_SHAPE,
    };
    if (slotting === null) {
        return {
            ...style,
            colorBy: null,
            opacityBy: null,
            sizeBy: null,
            pointColor: colors.point,
            pointColorActive: colors.selected,
            pointColorHover: colors.hover,
            opacity: point.opacity,
            pointSize: point.sizePx,
        };
    }
    const palette = paletteColors(coloring, colors);
    return {
        ...style,
        colorBy: CATEGORICAL_ENCODING,
        opacityBy: CATEGORICAL_ENCODING,
        sizeBy: CATEGORICAL_ENCODING,
        pointColor: [...palette],
        pointColorActive: perSlotColor(colors.selected, palette.length),
        pointColorHover: perSlotColor(colors.hover, palette.length),
        opacity: slotValues(slotting, point.opacity, point.substrateOpacity),
        pointSize: slotValues(slotting, point.sizePx, point.substrateSizePx),
    };
}

/** One draw's worth of points: the positions in the shape the scatterplot reads, and the order to draw them in. */
interface PointDrawing {
    readonly positions: number[][];
    readonly categorical: boolean;
    /** Every point's index, substrate first; null for a batch drawn in one flat color. */
    readonly order: number[] | null;
}

/**
 * The positions a draw hands the scatterplot: `[x, y, slot]` triples under regl-scatterplot's own
 * categorical coloring when every point carries a slot, or plain `[x, y]` pairs for a batch drawn in
 * one flat color -- the two tabs share one scatterplot instance (see `CloudPanel`), so this decides
 * per draw which of the two point kinds is on screen.
 */
function pointDrawing(points: readonly CloudEntityPoint[], slotting: PointSlots | null): PointDrawing {
    if (slotting === null) {
        return { positions: points.map((point) => [point.x, point.y]), categorical: false, order: null };
    }
    return {
        positions: points.map((point, index) => [point.x, point.y, slotting.slots[index] ?? slotting.substrateSlot]),
        categorical: true,
        order: drawOrder(slotting),
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

interface BandSegment extends ScreenSegment {
    /** Whether the far end snapped to the point under the cursor. */
    readonly endsOnPoint: boolean;
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

function sameBand(a: BandSegment | null, b: BandSegment | null): boolean {
    return a === null || b === null ? a === b : a.endsOnPoint === b.endsOnPoint && sameSegment(a, b);
}

function sameEntity(a: EntityRef, b: EntityRef): boolean {
    return a.kind === b.kind && a.hash === b.hash;
}

function sameHighlight(a: EntityRef | null, b: EntityRef | null): boolean {
    return a === null || b === null ? a === b : sameEntity(a, b);
}

/** Whether two camera views hold the same matrix; a missing one matches nothing. */
function sameView(first: Float32Array | null, second: Float32Array | null): boolean {
    return (
        first !== null &&
        second !== null &&
        first.length === second.length &&
        first.every((value, index) => value === second[index])
    );
}

/** The first index each hash takes among `points`, the same point `selectHighlighted` finds for it. */
function firstIndexByHash(points: readonly CloudEntityPoint[]): ReadonlyMap<string, number> {
    const indices = new Map<string, number>();
    points.forEach((point, index) => {
        if (!indices.has(point.ref.hash)) {
            indices.set(point.ref.hash, index);
        }
    });
    return indices;
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
    drawing: PointDrawing,
    appearance: ScatterplotProperties,
): Promise<void> {
    const runDraw = (): Promise<void> =>
        scatterplot
            .set(appearance)
            .then(() =>
                scatterplot.draw(drawing.positions, drawing.categorical ? { zDataType: CATEGORICAL_DATA } : undefined),
            );
    const next = chain.current.then(runDraw, runDraw);
    chain.current = next.then(
        () => undefined,
        () => undefined,
    );
    return next;
}

/** Everything one call to `applyPoints` draws and selects. */
interface PointsRequest {
    readonly points: readonly CloudEntityPoint[];
    readonly drawing: PointDrawing;
    readonly appearance: ScatterplotProperties;
    readonly highlighted: EntityRef | null;
}

/**
 * Draws the current points and applies whichever one (if any) is highlighted -- shared by the
 * mount effect, which needs this once right after a shape-driven recreation, and the effect that
 * tracks `points`/`highlighted` changes on an already-created scatterplot. Awaits the (serialized)
 * draw before touching selection: regl-scatterplot throws "Points have not been drawn" from
 * `getScreenPosition` (and a caller reading it right after `select` hits the same unset state) if
 * it's called before a first `draw` resolves, which a fresh scatterplot -- still compiling its
 * WebGL shaders -- does not do synchronously the way an already-drawn one redrawing existing points
 * effectively does. The draw order is handed over once the draw has resolved, since a draw of a
 * different number of points resets whatever order the scatterplot held. `isCanceled` reports true
 * once the effect that started this call has been cleaned up (its scatterplot destroyed, e.g. by an
 * unmount racing the pending draw, or replaced by a recreation), so its result goes unused.
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
    request: PointsRequest,
    isCanceled: () => boolean,
): Promise<number> {
    try {
        await drawSerialized(scatterplot, drawChain, request.drawing, request.appearance);
    } catch (error) {
        if (isCanceled()) {
            return -1;
        }
        throw error;
    }
    if (isCanceled()) {
        return -1;
    }

    void scatterplot.set({ pointOrder: request.drawing.order });
    return selectHighlighted(scatterplot, request.points, request.highlighted);
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
 * marks its screen position, pinned to the point through any pan or zoom while it plays. Selecting a point
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
 * `link` names two points in view, a line joins them and its marker is the weight; the hover
 * tracking pauses while the marker is dragged, since the library keeps hit-testing beneath it.
 *
 * The selected and the hovered point each carry a marker in the theme's point shape. Every overlay
 * -- the markers, the ping, the band and the link -- follows the library's `drawing` event, which
 * arrives within the frame that drew a moved view, and a resize of the container, and commits
 * before that frame paints, so the overlays move in step with the points.
 *
 * How the points look comes from the theme through `useCloudRenderSettings`: size, shape, opacity
 * and colors are handed to the library at creation and re-applied through its own `set` whenever
 * the theme changes. Points that carry a `category` (every sample-cloud point does; a module-cloud
 * point carries none) draw with regl-scatterplot's own categorical coloring, one color and one
 * opacity per palette slot, the substrate's slot -- the uncategorized samples, or those no painted
 * tag reaches -- fainter than the rest and drawn beneath it, so the classified structure stands on
 * a ground whose density still shows. The active and hover colors come as one per slot, which is
 * what paints a selected or hovered point in the theme's own selection and hover colors. The
 * library compiles a point's shape into its shaders at creation, so a theme that changes the shape
 * recreates the scatterplot, carrying the camera over so the view stays where it was.
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
    const scatterplotGenerationRef = useRef(0);
    const cameraViewRef = useRef<Float32Array | null>(null);
    const drawChainRef = useRef<Promise<void>>(Promise.resolve());
    // regl-scatterplot's `getScreenPosition` throws until the first `draw` resolves.
    const pointsDrawnRef = useRef(false);
    const pointsRef = useRef<readonly CloudEntityPoint[]>([]);
    const hoveredIndexRef = useRef<number | null>(null);
    const selectedIndexRef = useRef(-1);
    const lastViewRef = useRef<Float32Array | null>(null);
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
    const [band, setBand] = useState<BandSegment | null>(null);
    const [markers, setMarkers] = useState<MarkerPositions>(NO_MARKERS);

    const settings = useCloudRenderSettings();
    const pointShape = settings.point.shape;
    const devicePixelRatio = window.devicePixelRatio;
    const markerAppearance = useMemo(
        (): MarkerAppearance => ({ ...settings.marker, shape: pointShape, devicePixelRatio }),
        [settings, pointShape, devicePixelRatio],
    );
    const points = useMemo(() => normalizePoints(rawPoints), [rawPoints]);
    pointsRef.current = points;
    const slotting = useMemo(() => slotPoints(points, coloring), [points, coloring]);
    const slottingRef = useRef(slotting);
    slottingRef.current = slotting;
    const appearance = useMemo(() => pointAppearance(slotting, coloring, settings), [slotting, coloring, settings]);
    const appearanceRef = useRef(appearance);
    appearanceRef.current = appearance;
    const indexByHash = useMemo(() => firstIndexByHash(points), [points]);
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
        const next: BandSegment = {
            first: originPosition,
            second: hoveredPosition ?? cursor,
            endsOnPoint: hoveredPosition !== undefined,
        };
        setBand((current) => (sameBand(current, next) ? current : next));
    }, []);

    /** Pins the selected and hovered markers to their points, marking the hovered one only while it is another point. */
    const repinMarkers = useCallback((): void => {
        const scatterplot = scatterplotRef.current;
        if (scatterplot === null || !pointsDrawnRef.current) {
            setMarkers(NO_MARKERS);
            return;
        }
        const selectedIndex = selectedIndexRef.current;
        const hoveredIndex = hoveredIndexRef.current;
        const next: MarkerPositions = {
            selected: selectedIndex < 0 ? null : (scatterplot.getScreenPosition(selectedIndex) ?? null),
            hovered:
                hoveredIndex === null || hoveredIndex === selectedIndex
                    ? null
                    : (scatterplot.getScreenPosition(hoveredIndex) ?? null),
        };
        setMarkers((current) => (sameMarkers(current, next) ? current : next));
    }, []);

    const repinPing = useCallback((): void => {
        const scatterplot = scatterplotRef.current;
        const activePing = pingRef.current;
        if (scatterplot === null || activePing === null || !pointsDrawnRef.current) {
            return;
        }
        const position = scatterplot.getScreenPosition(activePing.pointIndex);
        if (position !== undefined && !samePosition(position, activePing.position)) {
            setPing({ ...activePing, position });
        }
    }, []);

    /**
     * Pins every overlay to the points it marks, committed before the frame paints: called from the
     * scatterplot's own drawing of a moved view and from a resize, so a ring, the link and the ping
     * move in the very frame the points do.
     */
    const repinOverlays = useCallback((): void => {
        flushSync(() => {
            repinLink();
            repinBand();
            repinPing();
            repinMarkers();
        });
    }, [repinLink, repinBand, repinPing, repinMarkers]);

    useEffect(() => {
        const container = containerRef.current;
        if (container === null) {
            return undefined;
        }

        const canvas = document.createElement("canvas");
        container.append(canvas);

        const cameraView = cameraViewRef.current;
        const scatterplot = createScatterplot({
            canvas,
            ...appearanceRef.current,
            ...(cameraView !== null && { cameraView }),
            renderPointsAsSquares: pointShape === SQUARE_SHAPE,
            deselectOnDblClick: false,
        });
        scatterplotRef.current = scatterplot;
        scatterplotGenerationRef.current += 1;
        const generation = scatterplotGenerationRef.current;
        pointsDrawnRef.current = false;
        lastViewRef.current = null;
        drawChainRef.current = Promise.resolve();
        let canceled = false;
        const isCanceled = (): boolean => canceled || scatterplotGenerationRef.current !== generation;
        void applyPoints(
            scatterplot,
            drawChainRef,
            {
                points: pointsRef.current,
                drawing: pointDrawing(pointsRef.current, slottingRef.current),
                appearance: appearanceRef.current,
                highlighted: highlightedRef.current,
            },
            isCanceled,
        ).then((highlightedIndex) => {
            if (!isCanceled()) {
                pointsDrawnRef.current = true;
                selectedIndexRef.current = highlightedIndex;
                repinLink();
                repinMarkers();
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
            repinMarkers();
        });
        const pointOutSubscription = scatterplot.subscribe("pointOut", () => {
            hoveredIndexRef.current = null;
            onHoverRef.current(null, null);
            repinBand();
            repinMarkers();
        });
        const deselectSubscription = scatterplot.subscribe("deselect", () => {
            onClearRef.current();
        });
        // The library publishes `view` a task after the frame it drew; `drawing` arrives within that frame.
        const drawingSubscription = scatterplot.subscribe("drawing", ({ view }) => {
            if (sameView(lastViewRef.current, view)) {
                return;
            }
            lastViewRef.current = Float32Array.from(view);
            repinOverlays();
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
            scatterplot.unsubscribe(drawingSubscription);
            cameraViewRef.current = Float32Array.from(scatterplot.get(CAMERA_VIEW_PROPERTY));
            scatterplot.destroy();
            scatterplotRef.current = null;
            canvas.remove();
        };
        // Created once per point shape, reading the rest at creation; the effects below update the live instance.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pointShape]);

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

        const generation = scatterplotGenerationRef.current;
        let canceled = false;
        const isCanceled = (): boolean => canceled || scatterplotGenerationRef.current !== generation;
        void applyPoints(
            scatterplot,
            drawChainRef,
            {
                points,
                drawing: pointDrawing(points, slotting),
                appearance: appearanceRef.current,
                highlighted: highlightedRef.current,
            },
            isCanceled,
        ).then((highlightedIndex) => {
            if (isCanceled()) {
                return;
            }

            pointsDrawnRef.current = true;
            selectedIndexRef.current = highlightedIndex;
            repinLink();
            repinMarkers();
            pingNewHighlight(scatterplot, highlightedIndex);
        });
        return (): void => {
            canceled = true;
        };
    }, [points, slotting, repinLink, repinMarkers, pingNewHighlight]);

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
            const highlightedIndex = selectHighlighted(scatterplot, pointsRef.current, highlighted);
            selectedIndexRef.current = highlightedIndex;
            repinMarkers();
            pingNewHighlight(scatterplot, highlightedIndex);
        });
        return (): void => {
            canceled = true;
        };
    }, [highlighted, repinMarkers, pingNewHighlight]);

    useEffect(() => {
        repinLink();
    }, [link, repinLink]);

    useEffect(() => {
        const container = containerRef.current;
        if (container === null) {
            return undefined;
        }
        const observer = new ResizeObserver(() => {
            repinOverlays();
        });
        observer.observe(container);
        return (): void => {
            observer.disconnect();
        };
    }, [repinOverlays]);

    // A new theme reaches the live scatterplot through `set`; a new coloring reaches it with its own draw.
    useEffect(() => {
        void scatterplotRef.current?.set(appearanceRef.current);
    }, [settings]);

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
            <CloudMarkers positions={markers} appearance={markerAppearance} />
            {ping !== null && (
                <span key={ping.key} className="cloud-ping" style={{ left: ping.position[0], top: ping.position[1] }}>
                    <span className="cloud-ping-ring" />
                    <span className="cloud-ping-ring cloud-ping-ring-delayed" />
                </span>
            )}
            {band !== null && (
                <MorphBand
                    origin={band.first}
                    cursor={band.second}
                    endsOnPoint={band.endsOnPoint}
                    appearance={markerAppearance}
                />
            )}
            {link !== null && linkScreen !== null && (
                <MorphLink
                    first={linkScreen.first}
                    second={linkScreen.second}
                    weight={link.weight}
                    appearance={markerAppearance}
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
