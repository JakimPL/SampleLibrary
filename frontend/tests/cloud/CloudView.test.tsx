import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type CloudCommand, type CloudLink, CloudView } from "../../src/cloud/CloudView";
import type { CloudEntityPoint } from "../../src/cloud/geometry";
import { type PointColoring, SUBSTRATE_ONLY_COLORING } from "../../src/cloud/labelColoring";
import { LONG_PRESS_HOLD_MS } from "../../src/shared/gestures/gestureThresholds";
import { useThemeStore } from "../../src/theme/themeStore";
import type { EntityRef } from "../../src/workspace/selectionStore";

const { instances, createScatterplotMock } = vi.hoisted(() => {
    class FakeScatterplot {
        readonly options: unknown;
        readonly draw = vi.fn().mockResolvedValue(undefined);
        readonly select = vi.fn();
        readonly deselect = vi.fn();
        readonly destroy = vi.fn();
        readonly set = vi.fn().mockResolvedValue(undefined);
        readonly getScreenPosition = vi.fn((index: number) => [10 + index, 20 + index] as [number, number]);
        readonly hover = vi.fn();
        readonly redraw = vi.fn();
        readonly zoomToArea = vi.fn().mockResolvedValue(undefined);
        readonly camera = { pan: vi.fn(), scale: vi.fn() };
        cameraView = new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
        readonly get = vi.fn((property: string) => {
            if (property === "cameraView") {
                return this.cameraView;
            }
            return property === "camera" ? this.camera : undefined;
        });
        private readonly listeners = new Map<string, ((payload: unknown) => void)[]>();

        constructor(options: unknown) {
            this.options = options;
        }

        subscribe(event: string, handler: (payload: unknown) => void): { event: string; handler: unknown } {
            const handlers = this.listeners.get(event) ?? [];
            handlers.push(handler);
            this.listeners.set(event, handlers);
            return { event, handler };
        }

        unsubscribe(): void {
            // subscriptions are torn down together with the instance in these tests
        }

        emit(event: string, payload?: unknown): void {
            for (const handler of this.listeners.get(event) ?? []) {
                handler(payload);
            }
        }
    }

    const instances: FakeScatterplot[] = [];
    const createScatterplotMock = vi.fn((options: unknown) => {
        const instance = new FakeScatterplot(options);
        instances.push(instance);
        return instance;
    });
    return { instances, createScatterplotMock };
});

vi.mock("regl-scatterplot", () => ({
    default: createScatterplotMock,
}));

function latestInstance(): (typeof instances)[number] {
    const instance = instances[instances.length - 1];
    if (instance === undefined) {
        throw new Error("no FakeScatterplot instance was created");
    }
    return instance;
}

function latestCanvas(): HTMLCanvasElement {
    const canvas = document.querySelector<HTMLCanvasElement>("canvas.cloud-dots");
    if (canvas === null) {
        throw new Error("canvas not found");
    }
    return canvas;
}

function point(ref: EntityRef, x: number, y: number): CloudEntityPoint {
    return { ref, x, y };
}

interface RenderOverrides {
    readonly points?: readonly CloudEntityPoint[];
    readonly coloring?: PointColoring;
    readonly highlighted?: EntityRef | null;
    readonly onSelect?: (entity: EntityRef) => void;
    readonly onFocus?: (entity: EntityRef) => void;
    readonly onClear?: () => void;
    readonly onHover?: (entity: EntityRef | null, screenPosition: readonly [number, number] | null) => void;
    readonly onJoinToAnchor?: (entity: EntityRef) => void;
    readonly onJoin?: (first: EntityRef, second: EntityRef) => void;
    readonly onActivate?: (entity: EntityRef) => void;
    readonly onContextMenu?: (entity: EntityRef, position: readonly [number, number]) => void;
    readonly pairing?: boolean;
    readonly onPairTap?: (entity: EntityRef) => void;
    readonly command?: CloudCommand | null;
    readonly link?: CloudLink | null;
    readonly anchor?: string | null;
}

/** Lets the fake scatterplot's `draw` promise settle, which CloudView awaits before selecting or deselecting. */
async function flushDraw(): Promise<void> {
    await act(async () => {
        await Promise.resolve();
    });
}

let viewCounter = 0;

/** A camera view no frame has drawn yet, as a pan or zoom would hand the library's `drawing` event. */
function movedView(): Float32Array {
    viewCounter += 1;
    return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, viewCounter, 0, 0, 1]);
}

/** Every prop the view takes, the given ones over inert defaults. */
function viewProps(overrides: RenderOverrides = {}): Parameters<typeof CloudView>[0] {
    return {
        coloring: overrides.coloring ?? SUBSTRATE_ONLY_COLORING,
        points: overrides.points ?? [],
        highlighted: overrides.highlighted ?? null,
        onSelect: overrides.onSelect ?? vi.fn(),
        onFocus: overrides.onFocus ?? vi.fn(),
        onClear: overrides.onClear ?? vi.fn(),
        onHover: overrides.onHover ?? vi.fn(),
        onJoinToAnchor: overrides.onJoinToAnchor ?? vi.fn(),
        onJoin: overrides.onJoin ?? vi.fn(),
        onActivate: overrides.onActivate ?? vi.fn(),
        onContextMenu: overrides.onContextMenu ?? vi.fn(),
        pairing: overrides.pairing ?? false,
        onPairTap: overrides.onPairTap ?? vi.fn(),
        command: overrides.command ?? null,
        link: overrides.link ?? null,
        onWeightChange: vi.fn(),
        onWeightCommit: vi.fn(),
        anchor: overrides.anchor ?? null,
    };
}

async function renderCloudView(overrides: RenderOverrides = {}): Promise<ReturnType<typeof render>> {
    const result = render(
        <CloudView
            coloring={overrides.coloring ?? SUBSTRATE_ONLY_COLORING}
            points={overrides.points ?? []}
            highlighted={overrides.highlighted ?? null}
            onSelect={overrides.onSelect ?? vi.fn()}
            onFocus={overrides.onFocus ?? vi.fn()}
            onClear={overrides.onClear ?? vi.fn()}
            onHover={overrides.onHover ?? vi.fn()}
            onJoinToAnchor={overrides.onJoinToAnchor ?? vi.fn()}
            onJoin={overrides.onJoin ?? vi.fn()}
            onActivate={overrides.onActivate ?? vi.fn()}
            onContextMenu={overrides.onContextMenu ?? vi.fn()}
            pairing={overrides.pairing ?? false}
            onPairTap={overrides.onPairTap ?? vi.fn()}
            command={overrides.command ?? null}
            link={overrides.link ?? null}
            onWeightChange={vi.fn()}
            onWeightCommit={vi.fn()}
            anchor={overrides.anchor ?? null}
        />,
    );
    await flushDraw();
    return result;
}

const RIGHT_BUTTON = 2;
const SAMPLE_REF: EntityRef = { kind: "sample", hash: "a".repeat(64) };
const OTHER_SAMPLE_REF: EntityRef = { kind: "sample", hash: "c".repeat(64) };
const MODULE_REF: EntityRef = { kind: "module", hash: "b".repeat(64) };

beforeEach(() => {
    instances.length = 0;
    createScatterplotMock.mockClear();
});

describe("CloudView", () => {
    it("shows an honest empty state when there are no cloud coordinates yet", async () => {
        await renderCloudView();

        expect(screen.getByText("No cloud coordinates yet")).toBeInTheDocument();
    });

    it("draws every given point through the scatterplot", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)] });

        const drawnPoints = latestInstance().draw.mock.calls[0]?.[0] as unknown[];
        expect(drawnPoints).toHaveLength(1);
    });

    it("reports the entity behind a point the library reports as clicked", async () => {
        const onSelect = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onSelect });

        latestInstance().emit("select", { points: [0] });

        expect(onSelect).toHaveBeenCalledWith(SAMPLE_REF);
    });

    it("reports a clicked point's entity through onActivate as well, for a caller to play it", async () => {
        const onActivate = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onActivate });

        latestInstance().emit("select", { points: [0] });

        expect(onActivate).toHaveBeenCalledWith(SAMPLE_REF);
    });

    it("does not ping a point selected by clicking it directly in this view", async () => {
        const { container, rerender } = await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)] });

        latestInstance().emit("select", { points: [0] });
        // After a real click, onSelect's entity returns to this view as its `highlighted` prop.
        rerender(
            <CloudView
                coloring={SUBSTRATE_ONLY_COLORING}
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onJoinToAnchor={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
                onContextMenu={vi.fn()}
                pairing={false}
                onPairTap={vi.fn()}
                command={null}
                link={null}
                onWeightChange={vi.fn()}
                onWeightCommit={vi.fn()}
                anchor={null}
            />,
        );
        await flushDraw();

        expect(container.querySelector(".cloud-ping")).not.toBeInTheDocument();
    });

    it("focuses the currently hovered entity on a native double-click", async () => {
        const onFocus = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onFocus });
        latestInstance().emit("pointOver", 0);

        fireEvent.dblClick(latestCanvas());

        expect(onFocus).toHaveBeenCalledWith(SAMPLE_REF);
    });

    it("does not focus anything on a double-click while the cursor is over no point", async () => {
        const onFocus = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onFocus });

        fireEvent.dblClick(latestCanvas());

        expect(onFocus).not.toHaveBeenCalled();
    });

    it("clears the highlight on a click that misses every point", async () => {
        const onClear = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onClear });

        fireEvent.click(latestCanvas());

        expect(onClear).toHaveBeenCalled();
    });

    it("reports a point right-clicked in place as a comparison target", async () => {
        const onJoinToAnchor = vi.fn();
        const onJoin = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onJoinToAnchor, onJoin });
        latestInstance().emit("pointOver", 0);

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON });
        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(onJoinToAnchor).toHaveBeenCalledWith(SAMPLE_REF);
        expect(onJoin).not.toHaveBeenCalled();
    });

    it("keeps the browser's menu off the canvas", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)] });

        expect(fireEvent.contextMenu(latestCanvas())).toBe(false);
    });

    it("does not report a comparison target on a plain click", async () => {
        const onJoinToAnchor = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onJoinToAnchor });
        latestInstance().emit("pointOver", 0);

        fireEvent.click(latestCanvas());

        expect(onJoinToAnchor).not.toHaveBeenCalled();
    });

    it("does not clear the highlight on a click over a point", async () => {
        const onClear = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onClear });
        latestInstance().emit("pointOver", 0);

        fireEvent.click(latestCanvas());

        expect(onClear).not.toHaveBeenCalled();
    });

    it("clears the highlight when the library reports its own deselect (e.g. Escape)", async () => {
        const onClear = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onClear });

        latestInstance().emit("deselect");

        expect(onClear).toHaveBeenCalled();
    });

    it("keeps the highlight through a click that ends a pan", async () => {
        const onClear = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onClear });

        fireEvent.mouseDown(latestCanvas(), { button: 0, clientX: 10, clientY: 10 });
        fireEvent.click(latestCanvas(), { button: 0, clientX: 60, clientY: 40 });

        expect(onClear).not.toHaveBeenCalled();
    });

    it("moves the highlight among the drawn points without drawing them again", async () => {
        const second: EntityRef = { kind: "sample", hash: "c".repeat(64) };
        const points = [point(SAMPLE_REF, 0, 0), point(second, 1, 1)];
        const { rerender } = await renderCloudView({ points, highlighted: SAMPLE_REF });
        const draws = latestInstance().draw.mock.calls.length;

        rerender(
            <CloudView
                coloring={SUBSTRATE_ONLY_COLORING}
                points={points}
                highlighted={second}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onJoinToAnchor={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
                onContextMenu={vi.fn()}
                pairing={false}
                onPairTap={vi.fn()}
                command={null}
                link={null}
                onWeightChange={vi.fn()}
                onWeightCommit={vi.fn()}
                anchor={null}
            />,
        );
        await flushDraw();

        expect(latestInstance().select).toHaveBeenLastCalledWith([1], { preventEvent: true });
        expect(latestInstance().draw.mock.calls.length).toBe(draws);
    });

    it("selects the highlighted point within the scatterplot itself", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: SAMPLE_REF });

        expect(latestInstance().select).toHaveBeenCalledWith([0], { preventEvent: true });
    });

    it("waits for the scatterplot's draw to resolve before selecting the highlighted point", async () => {
        render(
            <CloudView
                coloring={SUBSTRATE_ONLY_COLORING}
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onJoinToAnchor={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
                onContextMenu={vi.fn()}
                pairing={false}
                onPairTap={vi.fn()}
                command={null}
                link={null}
                onWeightChange={vi.fn()}
                onWeightCommit={vi.fn()}
                anchor={null}
            />,
        );

        expect(latestInstance().select).not.toHaveBeenCalled();

        await flushDraw();

        expect(latestInstance().select).toHaveBeenCalledWith([0], { preventEvent: true });
    });

    it("never starts a new draw before the previous one has settled, even under a burst of updates", async () => {
        const { rerender } = await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)],
        });
        const instance = latestInstance();

        let activeDraws = 0;
        let maxConcurrentDraws = 0;
        instance.draw.mockImplementation(() => {
            activeDraws += 1;
            maxConcurrentDraws = Math.max(maxConcurrentDraws, activeDraws);
            return Promise.resolve().then(() => {
                activeDraws -= 1;
            });
        });

        function rerenderWithHighlight(highlighted: EntityRef): void {
            rerender(
                <CloudView
                    coloring={SUBSTRATE_ONLY_COLORING}
                    points={[point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)]}
                    highlighted={highlighted}
                    onSelect={vi.fn()}
                    onFocus={vi.fn()}
                    onClear={vi.fn()}
                    onHover={vi.fn()}
                    onJoinToAnchor={vi.fn()}
                    onJoin={vi.fn()}
                    onActivate={vi.fn()}
                    onContextMenu={vi.fn()}
                    pairing={false}
                    onPairTap={vi.fn()}
                    command={null}
                    link={null}
                    onWeightChange={vi.fn()}
                    onWeightCommit={vi.fn()}
                    anchor={null}
                />,
            );
        }

        rerenderWithHighlight(SAMPLE_REF);
        rerenderWithHighlight(MODULE_REF);
        rerenderWithHighlight(SAMPLE_REF);

        await flushDraw();
        await flushDraw();
        await flushDraw();

        expect(maxConcurrentDraws).toBeLessThanOrEqual(1);
    });

    it("deselects when the current highlight matches nothing on this view", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: MODULE_REF });

        expect(latestInstance().deselect).toHaveBeenCalledWith({ preventEvent: true });
    });

    it("destroys the scatterplot instance when the component unmounts", async () => {
        const { unmount } = await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)] });
        const instance = latestInstance();

        unmount();

        expect(instance.destroy).toHaveBeenCalled();
    });

    it("reports the hovered entity and its screen position", async () => {
        const onHover = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onHover });

        latestInstance().emit("pointOver", 0);

        expect(onHover).toHaveBeenCalledWith(SAMPLE_REF, [10, 20]);
    });

    it("reports no hover once the cursor leaves the point", async () => {
        const onHover = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onHover });
        latestInstance().emit("pointOver", 0);

        latestInstance().emit("pointOut");

        expect(onHover).toHaveBeenLastCalledWith(null, null);
    });

    it("shows a sonar ping at a newly highlighted point", async () => {
        const { container } = await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: SAMPLE_REF });

        expect(container.querySelector(".cloud-ping")).toBeInTheDocument();
    });

    it("does not re-ping when the same highlight persists across a re-render", async () => {
        const { container, rerender } = await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0)],
            highlighted: SAMPLE_REF,
        });
        const firstPing = container.querySelector(".cloud-ping");

        rerender(
            <CloudView
                coloring={SUBSTRATE_ONLY_COLORING}
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onJoinToAnchor={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
                onContextMenu={vi.fn()}
                pairing={false}
                onPairTap={vi.fn()}
                command={null}
                link={null}
                onWeightChange={vi.fn()}
                onWeightCommit={vi.fn()}
                anchor={null}
            />,
        );
        await flushDraw();

        expect(container.querySelector(".cloud-ping")).toBe(firstPing);
    });

    it("does not re-ping when a value-equal but differently-referenced highlight is passed in", async () => {
        const { container, rerender } = await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0)],
            highlighted: SAMPLE_REF,
        });
        const firstPing = container.querySelector(".cloud-ping");

        rerender(
            <CloudView
                coloring={SUBSTRATE_ONLY_COLORING}
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={{ kind: SAMPLE_REF.kind, hash: SAMPLE_REF.hash }}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onJoinToAnchor={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
                onContextMenu={vi.fn()}
                pairing={false}
                onPairTap={vi.fn()}
                command={null}
                link={null}
                onWeightChange={vi.fn()}
                onWeightCommit={vi.fn()}
                anchor={null}
            />,
        );
        await flushDraw();

        expect(container.querySelector(".cloud-ping")).toBe(firstPing);
    });

    it("keeps the ping pinned to its point through a pan or zoom", async () => {
        const { container } = await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: SAMPLE_REF });
        const ping = container.querySelector<HTMLElement>(".cloud-ping");
        if (ping === null) {
            throw new Error("ping not found");
        }
        expect(ping.style.left).toBe("10px");

        latestInstance().getScreenPosition.mockReturnValue([120, 340]);
        act(() => {
            latestInstance().emit("drawing", { view: movedView() });
        });

        expect(ping.style.left).toBe("120px");
        expect(ping.style.top).toBe("340px");
    });

    it("creates the scatterplot with theme-driven point, active-point, and background colors", async () => {
        await renderCloudView();

        const options = createScatterplotMock.mock.calls[0]?.[0] as {
            pointColor?: string;
            pointColorActive?: string;
            backgroundColor?: string;
        };
        expect(options.pointColor).toBeTruthy();
        expect(options.pointColorActive).toBeTruthy();
        expect(options.backgroundColor).toBeTruthy();
    });

    it("re-applies colors through set when the theme preference changes", async () => {
        await renderCloudView();
        const instance = latestInstance();
        instance.set.mockClear();

        act(() => {
            useThemeStore.getState().setPreference("openmpt");
        });

        expect(instance.set).toHaveBeenCalled();
    });

    it("configures categorical coloring and draws slot triples when every point is a sample", async () => {
        await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0), point(OTHER_SAMPLE_REF, 1, 1)],
        });
        const instance = latestInstance();

        const setCall = instance.set.mock.calls[0]?.[0] as { colorBy?: string; pointColor?: unknown };
        expect(setCall.colorBy).toBe("category");
        expect(Array.isArray(setCall.pointColor)).toBe(true);
        const drawnPoints = instance.draw.mock.calls[0]?.[0] as number[][];
        expect(drawnPoints[0]).toHaveLength(3);
        expect(drawnPoints[1]).toHaveLength(3);
        expect(instance.draw.mock.calls[0]?.[1]).toEqual({ zDataType: "categorical" });
    });

    it("draws each point's painted-tag slot and a palette of one color per painted tag under a label coloring", async () => {
        const coloring: PointColoring = {
            slotByHash: new Map([[SAMPLE_REF.hash, 2]]),
            ranks: [5, 0],
        };
        await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0), point(OTHER_SAMPLE_REF, 1, 1)],
            coloring,
        });
        const instance = latestInstance();

        const setCall = instance.set.mock.calls[0]?.[0] as { colorBy?: string; pointColor?: string[] };
        expect(setCall.colorBy).toBe("category");
        expect(setCall.pointColor).toHaveLength(3);
        const drawnPoints = instance.draw.mock.calls[0]?.[0] as number[][];
        expect(drawnPoints[0]?.[2]).toBe(2);
        expect(drawnPoints[1]?.[2]).toBe(0);
        expect(instance.draw.mock.calls[0]?.[1]).toEqual({ zDataType: "categorical" });
    });

    it("draws flat [x, y] pairs under the plain point color for the module cloud", async () => {
        await renderCloudView({ points: [point(MODULE_REF, 0, 0)] });
        const instance = latestInstance();

        const setCall = instance.set.mock.calls[0]?.[0] as { colorBy?: string | null };
        expect(setCall.colorBy).toBeNull();
        const drawnPoints = instance.draw.mock.calls[0]?.[0] as number[][];
        expect(drawnPoints[0]).toHaveLength(2);
        expect(instance.draw.mock.calls[0]?.[1]).toBeUndefined();
    });

    it("falls back to flat coloring unless every point on this draw is a sample", async () => {
        await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)],
        });
        const instance = latestInstance();

        const setCall = instance.set.mock.calls[0]?.[0] as { colorBy?: string | null };
        expect(setCall.colorBy).toBeNull();
    });
});

describe("CloudView morph link", () => {
    const LINK: CloudLink = { first: SAMPLE_REF.hash, second: MODULE_REF.hash, weight: 0.5 };

    it("joins two points in view with a line whose marker sits at the weight", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)], link: LINK });

        const marker = screen.getByRole("slider", { name: "Morph weight" });
        expect(marker.style.left).toBe("10.5px");
        expect(marker.style.top).toBe("20.5px");
    });

    it("keeps the link pinned to its points through a pan or zoom", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)], link: LINK });

        latestInstance().getScreenPosition.mockReturnValue([120, 340]);
        act(() => {
            latestInstance().emit("drawing", { view: movedView() });
        });

        const marker = screen.getByRole("slider", { name: "Morph weight" });
        expect(marker.style.left).toBe("120px");
        expect(marker.style.top).toBe("340px");
    });

    it("shows no link while an end is out of this view", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], link: LINK });

        expect(screen.queryByRole("slider", { name: "Morph weight" })).not.toBeInTheDocument();
    });
});

describe("CloudView right-button pairing", () => {
    const TWO_POINTS: readonly CloudEntityPoint[] = [point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)];

    function bandLine(container: HTMLElement): SVGLineElement | null {
        return container.querySelector<SVGLineElement>(".morph-band-line");
    }

    interface Segment {
        readonly x1: number;
        readonly y1: number;
        readonly x2: number;
        readonly y2: number;
    }

    function segmentOf(line: SVGLineElement | null): Segment {
        if (line === null) {
            throw new Error("band line not found");
        }
        const read = (name: string): number => Number(line.getAttribute(name));
        return { x1: read("x1"), y1: read("y1"), x2: read("x2"), y2: read("y2") };
    }

    /** Whether `point` lies on the ray from `from` toward `toward`, strictly past `from`. */
    function liesAhead(
        from: readonly [number, number],
        toward: readonly [number, number],
        point: readonly [number, number],
    ): boolean {
        const alongX = toward[0] - from[0];
        const alongY = toward[1] - from[1];
        const offsetX = point[0] - from[0];
        const offsetY = point[1] - from[1];
        return Math.abs(alongX * offsetY - alongY * offsetX) < 1e-6 && alongX * offsetX + alongY * offsetY > 0;
    }

    /** Spreads the fake's points far enough apart that a band between two of them outreaches their markers. */
    function spreadPoints(): void {
        latestInstance().getScreenPosition.mockImplementation((index: number) => [10 + index * 100, 20 + index * 100]);
    }

    it("stretches a band from the pressed point's marker to the cursor while the right button is held", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS });
        latestInstance().emit("pointOver", 0);

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 10, clientY: 20 });
        fireEvent.mouseMove(latestCanvas(), { clientX: 50, clientY: 60 });

        const segment = segmentOf(bandLine(container));
        expect(liesAhead([10, 20], [50, 60], [segment.x1, segment.y1])).toBe(true);
        expect(container.querySelector(".morph-band-origin .cloud-marker-stroke")).toHaveAttribute("cx", "10");
        expect(segment.x2).toBe(50);
        expect(segment.y2).toBe(60);
    });

    it("snaps the band's far end to the point under the cursor, stopping at its marker", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS });
        spreadPoints();
        latestInstance().emit("pointOver", 0);
        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 10, clientY: 20 });
        fireEvent.mouseMove(latestCanvas(), { clientX: 50, clientY: 60 });

        act(() => {
            latestInstance().emit("pointOver", 1);
        });

        const segment = segmentOf(bandLine(container));
        expect(liesAhead([110, 120], [10, 20], [segment.x2, segment.y2])).toBe(true);
        expect(container.querySelector(".cloud-marker-hover .cloud-marker-stroke")).toHaveAttribute("cx", "110");
    });

    it("joins the pressed point to the one the button is released over, and drops the band", async () => {
        const onJoin = vi.fn();
        const onJoinToAnchor = vi.fn();
        const { container } = await renderCloudView({ points: TWO_POINTS, onJoin, onJoinToAnchor });
        latestInstance().emit("pointOver", 0);
        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 10, clientY: 20 });
        latestInstance().emit("pointOver", 1);

        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(onJoin).toHaveBeenCalledWith(SAMPLE_REF, MODULE_REF);
        expect(onJoinToAnchor).not.toHaveBeenCalled();
        expect(bandLine(container)).not.toBeInTheDocument();
    });

    it("starts the band from the anchor when the press lands on empty space", async () => {
        const onJoin = vi.fn();
        const { container } = await renderCloudView({ points: TWO_POINTS, anchor: SAMPLE_REF.hash, onJoin });

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 50, clientY: 60 });
        fireEvent.mouseMove(latestCanvas(), { clientX: 70, clientY: 80 });

        const segment = segmentOf(bandLine(container));
        expect(container.querySelector(".morph-band-origin .cloud-marker-stroke")).toHaveAttribute("cx", "10");
        expect(liesAhead([10, 20], [70, 80], [segment.x1, segment.y1])).toBe(true);
        expect(segment.x2).toBe(70);

        act(() => {
            latestInstance().emit("pointOver", 1);
        });
        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(onJoin).toHaveBeenCalledWith(SAMPLE_REF, MODULE_REF);
    });

    it("joins nothing when the button is released over empty space", async () => {
        const onJoin = vi.fn();
        const onJoinToAnchor = vi.fn();
        await renderCloudView({ points: TWO_POINTS, onJoin, onJoinToAnchor });
        latestInstance().emit("pointOver", 0);
        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 10, clientY: 20 });
        latestInstance().emit("pointOut");

        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(onJoin).not.toHaveBeenCalled();
        expect(onJoinToAnchor).not.toHaveBeenCalled();
    });

    it("draws no band for the left button", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS, anchor: SAMPLE_REF.hash });
        latestInstance().emit("pointOver", 0);

        fireEvent.mouseDown(latestCanvas(), { button: 0, clientX: 10, clientY: 20 });
        fireEvent.mouseMove(latestCanvas(), { clientX: 50, clientY: 60 });

        expect(bandLine(container)).not.toBeInTheDocument();
    });

    it("draws no band from empty space while no sample anchors the next morph", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS });

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 50, clientY: 60 });
        fireEvent.mouseMove(latestCanvas(), { clientX: 70, clientY: 80 });

        expect(bandLine(container)).not.toBeInTheDocument();
    });
});

describe("CloudView point appearance", () => {
    const THEME_PROPERTIES = [
        "--cloud-point-opacity",
        "--cloud-substrate-opacity",
        "--cloud-point-shape",
        "--cloud-point-selected",
        "--cloud-hover-color",
    ];

    afterEach(() => {
        for (const property of THEME_PROPERTIES) {
            document.documentElement.style.removeProperty(property);
        }
    });

    function lastPropertiesWith(instance: (typeof instances)[number], key: string): Record<string, unknown> {
        const matching = instance.set.mock.calls
            .map((call) => call[0] as Record<string, unknown>)
            .filter((properties) => key in properties);
        const properties = matching[matching.length - 1];
        if (properties === undefined) {
            throw new Error(`no set call carried ${key}`);
        }
        return properties;
    }

    function sample(hashCharacter: string): CloudEntityPoint {
        return point({ kind: "sample", hash: hashCharacter.repeat(64) }, 0, 0);
    }

    /** Samples "1" and "3" carry painted tags; "2" and "4" lie on the ground. */
    const PAINTED: PointColoring = {
        slotByHash: new Map([
            ["1".repeat(64), 1],
            ["3".repeat(64), 2],
        ]),
        ranks: [0, 1],
    };

    it("paints a categorical point's selected and hovered states in the theme's own colors, one per slot", async () => {
        document.documentElement.style.setProperty("--cloud-point-selected", "#ffff00");
        document.documentElement.style.setProperty("--cloud-hover-color", "#ffffff");
        await renderCloudView({ points: [sample("1"), sample("3")], coloring: PAINTED });

        const properties = lastPropertiesWith(latestInstance(), "pointColorActive");
        const palette = properties.pointColor as string[];
        expect(properties.pointColorActive).toEqual(palette.map(() => "#ffff00"));
        expect(properties.pointColorHover).toEqual(palette.map(() => "#ffffff"));
    });

    it("gives the substrate's slot its own opacity and every other slot the named points' one", async () => {
        document.documentElement.style.setProperty("--cloud-point-opacity", "0.8");
        document.documentElement.style.setProperty("--cloud-substrate-opacity", "0.3");
        await renderCloudView({ points: [sample("1"), sample("2")], coloring: PAINTED });

        const properties = lastPropertiesWith(latestInstance(), "opacity");
        expect(properties.opacityBy).toBe("category");
        expect(properties.opacity).toEqual([0.3, 0.8, 0.8]);
    });

    it("draws the substrate's points beneath the named ones once the points are drawn", async () => {
        await renderCloudView({
            points: [sample("1"), sample("2"), sample("3"), sample("4")],
            coloring: PAINTED,
        });

        expect(latestInstance().set).toHaveBeenCalledWith({ pointOrder: [1, 3, 0, 2] });
    });

    it("draws a batch of one flat color in its own order", async () => {
        await renderCloudView({ points: [point(MODULE_REF, 0, 0)] });

        expect(latestInstance().set).toHaveBeenCalledWith({ pointOrder: null });
    });

    it("recreates the scatterplot when a theme changes the point shape, keeping its camera, points and highlight", async () => {
        const points = [sample("1"), sample("2")];
        const highlighted = points[1]?.ref ?? null;
        await renderCloudView({ points, highlighted });
        const first = latestInstance();
        first.cameraView = new Float32Array([2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1, 0, 0.5, -0.25, 0, 1]);

        document.documentElement.style.setProperty("--cloud-point-shape", "square");
        act(() => {
            useThemeStore.getState().setPreference("openmpt");
        });
        await flushDraw();

        const second = latestInstance();
        const options = second.options as { renderPointsAsSquares?: boolean; cameraView?: Float32Array };
        expect(second).not.toBe(first);
        expect(first.destroy).toHaveBeenCalled();
        expect(options.renderPointsAsSquares).toBe(true);
        expect(options.cameraView).toEqual(first.cameraView);
        expect(second.draw.mock.calls[0]?.[0]).toHaveLength(points.length);
        expect(second.select).toHaveBeenCalledWith([1], { preventEvent: true });
    });

    it("keeps one scatterplot through a theme change that keeps the point shape", async () => {
        await renderCloudView({ points: [sample("1")] });

        act(() => {
            useThemeStore.getState().setPreference("dark");
        });
        await flushDraw();

        expect(instances).toHaveLength(1);
    });
});

describe("CloudView markers", () => {
    const TWO_POINTS: readonly CloudEntityPoint[] = [point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)];

    afterEach(() => {
        document.documentElement.style.removeProperty("--cloud-point-shape");
    });

    function marker(container: HTMLElement, kind: "hover" | "selected"): SVGElement | null {
        return container.querySelector<SVGElement>(`.cloud-marker-${kind} .cloud-marker-stroke`);
    }

    it("marks the hovered point, and drops the mark once the cursor leaves it", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS });

        act(() => {
            latestInstance().emit("pointOver", 1);
        });

        expect(marker(container, "hover")).toHaveAttribute("cx", "11");
        expect(marker(container, "hover")).toHaveAttribute("cy", "21");

        act(() => {
            latestInstance().emit("pointOut");
        });

        expect(marker(container, "hover")).not.toBeInTheDocument();
    });

    it("marks the highlighted point, and hovering it keeps the one mark", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS, highlighted: MODULE_REF });

        expect(marker(container, "selected")).toHaveAttribute("cx", "11");

        act(() => {
            latestInstance().emit("pointOver", 1);
        });

        expect(marker(container, "selected")).toBeInTheDocument();
        expect(marker(container, "hover")).not.toBeInTheDocument();
    });

    it("moves the marks with a frame that draws a moved view", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS, highlighted: SAMPLE_REF });
        act(() => {
            latestInstance().emit("pointOver", 1);
        });

        latestInstance().getScreenPosition.mockReturnValue([120, 340]);
        act(() => {
            latestInstance().emit("drawing", { view: movedView() });
        });

        expect(marker(container, "selected")).toHaveAttribute("cx", "120");
        expect(marker(container, "hover")).toHaveAttribute("cy", "340");
    });

    it("keeps the marks in place through a frame that draws the view already shown", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS, highlighted: SAMPLE_REF });
        const view = movedView();
        act(() => {
            latestInstance().emit("drawing", { view });
        });

        latestInstance().getScreenPosition.mockReturnValue([120, 340]);
        act(() => {
            latestInstance().emit("drawing", { view: Float32Array.from(view) });
        });

        expect(marker(container, "selected")).toHaveAttribute("cx", "10");
    });

    it("ends the hover along with a scatterplot that a theme's point shape replaces", async () => {
        const onHover = vi.fn();
        act(() => {
            useThemeStore.getState().setPreference("dark");
        });
        const { container } = await renderCloudView({ points: TWO_POINTS, onHover });
        act(() => {
            latestInstance().emit("pointOver", 1);
        });

        document.documentElement.style.setProperty("--cloud-point-shape", "square");
        act(() => {
            useThemeStore.getState().setPreference("openmpt");
        });
        await flushDraw();

        expect(instances).toHaveLength(2);
        expect(onHover).toHaveBeenLastCalledWith(null, null);
        expect(marker(container, "hover")).not.toBeInTheDocument();
    });

    it("draws square marks under a theme with square points", async () => {
        document.documentElement.style.setProperty("--cloud-point-shape", "square");
        const { container } = await renderCloudView({ points: TWO_POINTS, highlighted: SAMPLE_REF });

        expect(container.querySelector(".cloud-marker-selected rect.cloud-marker-stroke")).toBeInTheDocument();
    });
});

describe("CloudView node layer", () => {
    const GRID_SIDE = 150;

    afterEach(() => {
        document.documentElement.style.removeProperty("--cloud-node-mode");
    });

    /** Enough points spread over the whole data space that no marker would stay legible with all of them in view. */
    function crowdedPoints(): readonly CloudEntityPoint[] {
        return Array.from({ length: GRID_SIDE * GRID_SIDE }, (_, index) =>
            point(
                { kind: "sample", hash: index.toString(16).padStart(64, "0") },
                index % GRID_SIDE,
                Math.floor(index / GRID_SIDE),
            ),
        );
    }

    function nodesShown(container: HTMLElement): boolean {
        return container.querySelector(".cloud-wrap")?.classList.contains("cloud-wrap-nodes") ?? false;
    }

    it("draws the points as markers while the view holds few of them", async () => {
        const { container } = await renderCloudView({ points: [point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)] });

        expect(container.querySelector("canvas.cloud-nodes")).toBeInTheDocument();
        expect(nodesShown(container)).toBe(true);
    });

    it("keeps the dots while the view holds too many points, and turns to markers once a frame zooms in", async () => {
        const { container } = await renderCloudView({ points: crowdedPoints() });

        expect(nodesShown(container)).toBe(false);

        act(() => {
            latestInstance().emit("drawing", {
                view: new Float32Array([40, 0, 0, 0, 0, 40, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
            });
        });

        expect(nodesShown(container)).toBe(true);
    });

    it("draws markers at every zoom under a theme that always does", async () => {
        document.documentElement.style.setProperty("--cloud-node-mode", "always");
        const { container } = await renderCloudView({ points: crowdedPoints() });

        expect(nodesShown(container)).toBe(true);
    });
});

describe("CloudView touch", () => {
    // Normalized to (-1, -1) and (1, 1), which the 600px test surface shows at (0, 600) and (600, 0).
    const TWO_POINTS: readonly CloudEntityPoint[] = [point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)];
    const FINGER = { pointerId: 1, pointerType: "touch" };
    const OTHER_FINGER = { pointerId: 2, pointerType: "touch" };

    afterEach(() => {
        vi.useRealTimers();
    });

    function fingerDown(x: number, y: number, finger = FINGER): void {
        fireEvent.pointerDown(latestCanvas(), { ...finger, clientX: x, clientY: y });
    }

    function fingerMove(x: number, y: number, finger = FINGER): void {
        fireEvent.pointerMove(latestCanvas(), { ...finger, clientX: x, clientY: y });
    }

    function fingerUp(x: number, y: number, finger = FINGER): void {
        fireEvent.pointerUp(latestCanvas(), { ...finger, clientX: x, clientY: y });
    }

    function tap(x: number, y: number): void {
        fingerDown(x, y);
        fingerUp(x, y);
    }

    it("selects, reports and activates the point a finger taps, at once", async () => {
        const onSelect = vi.fn();
        const onActivate = vi.fn();
        await renderCloudView({ points: TWO_POINTS, onSelect, onActivate });

        tap(5, 595);

        expect(latestInstance().select).toHaveBeenCalledWith([0], { preventEvent: true });
        expect(onSelect).toHaveBeenCalledWith(SAMPLE_REF);
        expect(onActivate).toHaveBeenCalledWith(SAMPLE_REF);
    });

    it("clears the highlight on a tap that lands on no point", async () => {
        const onClear = vi.fn();
        const onSelect = vi.fn();
        await renderCloudView({ points: TWO_POINTS, onClear, onSelect });

        tap(300, 300);

        expect(onClear).toHaveBeenCalledTimes(1);
        expect(onSelect).not.toHaveBeenCalled();
    });

    it("pans the view with one finger and asks for the frame that shows it", async () => {
        await renderCloudView({ points: TWO_POINTS });

        fingerDown(100, 100);
        fingerMove(130, 115);

        expect(latestInstance().camera.pan).toHaveBeenCalledWith([0.1, -0.05]);
        expect(latestInstance().redraw).toHaveBeenCalled();
    });

    it("zooms about two fingers as they spread", async () => {
        await renderCloudView({ points: TWO_POINTS });

        fingerDown(200, 300);
        fingerDown(300, 300, OTHER_FINGER);
        fingerMove(400, 300, OTHER_FINGER);

        expect(latestInstance().camera.scale).toHaveBeenCalledWith([2, 2], [0, 0]);
        expect(latestInstance().camera.pan).toHaveBeenCalledWith([expect.closeTo(1 / 6, 5), expect.closeTo(0, 5)]);
    });

    it("reports a point a finger holds, with where it stands", async () => {
        const onContextMenu = vi.fn();
        await renderCloudView({ points: TWO_POINTS, onContextMenu });
        vi.useFakeTimers();

        fingerDown(5, 595);
        act(() => {
            vi.advanceTimersByTime(LONG_PRESS_HOLD_MS);
        });
        fingerUp(5, 595);

        expect(onContextMenu).toHaveBeenCalledWith(SAMPLE_REF, [10, 20]);
    });

    it("names a tapped point as an end of the pair while pairing, highlighting nothing", async () => {
        const onPairTap = vi.fn();
        const onSelect = vi.fn();
        await renderCloudView({ points: TWO_POINTS, pairing: true, onPairTap, onSelect });

        tap(5, 595);

        expect(onPairTap).toHaveBeenCalledWith(SAMPLE_REF);
        expect(onSelect).not.toHaveBeenCalled();
    });

    it("joins the point a finger drags from to the one it lifts over while pairing, showing the band between", async () => {
        const onJoin = vi.fn();
        const { container } = await renderCloudView({ points: TWO_POINTS, pairing: true, onJoin });

        fingerDown(5, 595);
        fingerMove(300, 300);
        expect(container.querySelector(".morph-band-line")).toBeInTheDocument();
        fingerMove(595, 5);
        fingerUp(595, 5);

        expect(onJoin).toHaveBeenCalledWith(SAMPLE_REF, MODULE_REF);
        expect(container.querySelector(".morph-band-line")).not.toBeInTheDocument();
    });

    it("leaves a mouse press to the scatterplot", async () => {
        const onSelect = vi.fn();
        await renderCloudView({ points: TWO_POINTS, onSelect });

        fireEvent.pointerDown(latestCanvas(), { pointerId: 1, pointerType: "mouse", clientX: 5, clientY: 595 });
        fireEvent.pointerUp(latestCanvas(), { pointerId: 1, pointerType: "mouse", clientX: 5, clientY: 595 });

        expect(onSelect).not.toHaveBeenCalled();
        expect(latestInstance().camera.pan).not.toHaveBeenCalled();
    });

    it("centers the view on a located point, and steps the zoom, on command", async () => {
        const { rerender } = await renderCloudView({ points: TWO_POINTS });

        rerender(
            <CloudView
                {...viewProps({
                    points: TWO_POINTS,
                    command: { sequence: 1, action: { kind: "locate", hash: SAMPLE_REF.hash } },
                })}
            />,
        );

        const [area, options] = latestInstance().zoomToArea.mock.calls[0] as [Record<string, number>, unknown];
        expect(area.x).toBeCloseTo(-1.15, 5);
        expect(area.y).toBeCloseTo(-1.15, 5);
        expect(area.width).toBeCloseTo(0.3, 5);
        expect(area.height).toBeCloseTo(0.3, 5);
        expect(options).toEqual({ transition: true, transitionDuration: 500 });

        rerender(
            <CloudView
                {...viewProps({ points: TWO_POINTS, command: { sequence: 2, action: { kind: "zoom", factor: 1.5 } } })}
            />,
        );

        expect(latestInstance().camera.scale).toHaveBeenCalledWith([1.5, 1.5], [0, 0]);
        expect(latestInstance().redraw).toHaveBeenCalled();
    });

    it("frames both ends of a pair with room around them, on command", async () => {
        const { rerender } = await renderCloudView({ points: TWO_POINTS });

        rerender(
            <CloudView
                {...viewProps({
                    points: TWO_POINTS,
                    command: {
                        sequence: 1,
                        action: { kind: "frame", first: SAMPLE_REF.hash, second: MODULE_REF.hash },
                    },
                })}
            />,
        );

        const [area, options] = latestInstance().zoomToArea.mock.calls[0] as [Record<string, number>, unknown];
        expect(area.x).toBeCloseTo(-1.5, 5);
        expect(area.y).toBeCloseTo(-1.5, 5);
        expect(area.width).toBeCloseTo(3, 5);
        expect(area.height).toBeCloseTo(3, 5);
        expect(options).toEqual({ transition: true, transitionDuration: 500 });
    });
});
