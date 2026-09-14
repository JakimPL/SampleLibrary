import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type CloudLink, CloudView } from "../../src/cloud/CloudView";
import type { CloudEntityPoint } from "../../src/cloud/geometry";
import type { PointColoring } from "../../src/cloud/labelColoring";
import { categoryIndex } from "../../src/samples/category";
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
        cameraView = new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
        readonly get = vi.fn((property: string) => (property === "cameraView" ? this.cameraView : undefined));
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
    const canvas = document.querySelector("canvas");
    if (canvas === null) {
        throw new Error("canvas not found");
    }
    return canvas;
}

function point(ref: EntityRef, x: number, y: number, category?: CloudEntityPoint["category"]): CloudEntityPoint {
    return category === undefined ? { ref, x, y } : { ref, x, y, category };
}

interface RenderOverrides {
    readonly points?: readonly CloudEntityPoint[];
    readonly coloring?: PointColoring;
    readonly highlighted?: EntityRef | null;
    readonly onSelect?: (entity: EntityRef) => void;
    readonly onFocus?: (entity: EntityRef) => void;
    readonly onClear?: () => void;
    readonly onHover?: (entity: EntityRef | null, screenPosition: readonly [number, number] | null) => void;
    readonly onCompare?: (entity: EntityRef) => void;
    readonly onJoin?: (first: EntityRef, second: EntityRef) => void;
    readonly onActivate?: (entity: EntityRef) => void;
    readonly link?: CloudLink | null;
    readonly anchor?: string | null;
}

/** Lets the fake scatterplot's `draw` promise settle, which CloudView awaits before selecting or deselecting. */
async function flushDraw(): Promise<void> {
    await act(async () => {
        await Promise.resolve();
    });
}

async function renderCloudView(overrides: RenderOverrides = {}): Promise<ReturnType<typeof render>> {
    const result = render(
        <CloudView
            coloring={overrides.coloring ?? CATEGORY_COLORING}
            points={overrides.points ?? []}
            highlighted={overrides.highlighted ?? null}
            onSelect={overrides.onSelect ?? vi.fn()}
            onFocus={overrides.onFocus ?? vi.fn()}
            onClear={overrides.onClear ?? vi.fn()}
            onHover={overrides.onHover ?? vi.fn()}
            onCompare={overrides.onCompare ?? vi.fn()}
            onJoin={overrides.onJoin ?? vi.fn()}
            onActivate={overrides.onActivate ?? vi.fn()}
            link={overrides.link ?? null}
            onWeightChange={vi.fn()}
            onWeightCommit={vi.fn()}
            anchor={overrides.anchor ?? null}
        />,
    );
    await flushDraw();
    return result;
}

const CATEGORY_COLORING: PointColoring = { kind: "category" };
const RIGHT_BUTTON = 2;
const SAMPLE_REF: EntityRef = { kind: "sample", hash: "a".repeat(64) };
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
                coloring={CATEGORY_COLORING}
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onCompare={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
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
        const onCompare = vi.fn();
        const onJoin = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onCompare, onJoin });
        latestInstance().emit("pointOver", 0);

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON });
        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(onCompare).toHaveBeenCalledWith(SAMPLE_REF);
        expect(onJoin).not.toHaveBeenCalled();
    });

    it("keeps the browser's menu off the canvas", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)] });

        expect(fireEvent.contextMenu(latestCanvas())).toBe(false);
    });

    it("does not report a comparison target on a plain click", async () => {
        const onCompare = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onCompare });
        latestInstance().emit("pointOver", 0);

        fireEvent.click(latestCanvas());

        expect(onCompare).not.toHaveBeenCalled();
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
                coloring={CATEGORY_COLORING}
                points={points}
                highlighted={second}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onCompare={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
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
                coloring={CATEGORY_COLORING}
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onCompare={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
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
                    coloring={CATEGORY_COLORING}
                    points={[point(SAMPLE_REF, 0, 0), point(MODULE_REF, 1, 1)]}
                    highlighted={highlighted}
                    onSelect={vi.fn()}
                    onFocus={vi.fn()}
                    onClear={vi.fn()}
                    onHover={vi.fn()}
                    onCompare={vi.fn()}
                    onJoin={vi.fn()}
                    onActivate={vi.fn()}
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
                coloring={CATEGORY_COLORING}
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onCompare={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
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
                coloring={CATEGORY_COLORING}
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={{ kind: SAMPLE_REF.kind, hash: SAMPLE_REF.hash }}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onCompare={vi.fn()}
                onJoin={vi.fn()}
                onActivate={vi.fn()}
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
            latestInstance().emit("view");
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

    it("configures categorical coloring and draws category-index triples when every point carries a category", async () => {
        await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0, "kick"), point(MODULE_REF, 1, 1, "snare")],
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
            kind: "label",
            slotByHash: new Map([[SAMPLE_REF.hash, 2]]),
            ranks: [5, 0],
        };
        await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0, "kick"), point(MODULE_REF, 1, 1, "snare")],
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

    it("draws flat [x, y] pairs under the plain point color when no point carries a category", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)] });
        const instance = latestInstance();

        const setCall = instance.set.mock.calls[0]?.[0] as { colorBy?: string | null };
        expect(setCall.colorBy).toBeNull();
        const drawnPoints = instance.draw.mock.calls[0]?.[0] as number[][];
        expect(drawnPoints[0]).toHaveLength(2);
        expect(instance.draw.mock.calls[0]?.[1]).toBeUndefined();
    });

    it("falls back to flat coloring when only some points on this draw carry a category", async () => {
        await renderCloudView({
            points: [point(SAMPLE_REF, 0, 0, "kick"), point(MODULE_REF, 1, 1)],
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
            latestInstance().emit("view");
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

    it("stretches a band from the pressed point to the cursor while the right button is held", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS });
        latestInstance().emit("pointOver", 0);

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 10, clientY: 20 });
        fireEvent.mouseMove(latestCanvas(), { clientX: 50, clientY: 60 });

        const line = bandLine(container);
        expect(line).toHaveAttribute("x1", "10");
        expect(line).toHaveAttribute("y1", "20");
        expect(line).toHaveAttribute("x2", "50");
        expect(line).toHaveAttribute("y2", "60");
    });

    it("snaps the band's far end to the point under the cursor", async () => {
        const { container } = await renderCloudView({ points: TWO_POINTS });
        latestInstance().emit("pointOver", 0);
        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 10, clientY: 20 });
        fireEvent.mouseMove(latestCanvas(), { clientX: 50, clientY: 60 });

        act(() => {
            latestInstance().emit("pointOver", 1);
        });

        expect(bandLine(container)).toHaveAttribute("x2", "11");
        expect(bandLine(container)).toHaveAttribute("y2", "21");
    });

    it("joins the pressed point to the one the button is released over, and drops the band", async () => {
        const onJoin = vi.fn();
        const onCompare = vi.fn();
        const { container } = await renderCloudView({ points: TWO_POINTS, onJoin, onCompare });
        latestInstance().emit("pointOver", 0);
        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 10, clientY: 20 });
        latestInstance().emit("pointOver", 1);

        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(onJoin).toHaveBeenCalledWith(SAMPLE_REF, MODULE_REF);
        expect(onCompare).not.toHaveBeenCalled();
        expect(bandLine(container)).not.toBeInTheDocument();
    });

    it("starts the band from the anchor when the press lands on empty space", async () => {
        const onJoin = vi.fn();
        const { container } = await renderCloudView({ points: TWO_POINTS, anchor: SAMPLE_REF.hash, onJoin });

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 50, clientY: 60 });
        fireEvent.mouseMove(latestCanvas(), { clientX: 70, clientY: 80 });

        expect(bandLine(container)).toHaveAttribute("x1", "10");
        expect(bandLine(container)).toHaveAttribute("y1", "20");
        expect(bandLine(container)).toHaveAttribute("x2", "70");

        act(() => {
            latestInstance().emit("pointOver", 1);
        });
        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(onJoin).toHaveBeenCalledWith(SAMPLE_REF, MODULE_REF);
    });

    it("joins nothing when the button is released over empty space", async () => {
        const onJoin = vi.fn();
        const onCompare = vi.fn();
        await renderCloudView({ points: TWO_POINTS, onJoin, onCompare });
        latestInstance().emit("pointOver", 0);
        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON, clientX: 10, clientY: 20 });
        latestInstance().emit("pointOut");

        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(onJoin).not.toHaveBeenCalled();
        expect(onCompare).not.toHaveBeenCalled();
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

    function sample(hashCharacter: string, category: CloudEntityPoint["category"]): CloudEntityPoint {
        return point({ kind: "sample", hash: hashCharacter.repeat(64) }, 0, 0, category);
    }

    it("paints a categorical point's selected and hovered states in the theme's own colors, one per slot", async () => {
        document.documentElement.style.setProperty("--cloud-point-selected", "#ffff00");
        document.documentElement.style.setProperty("--cloud-hover-color", "#ffffff");
        await renderCloudView({ points: [sample("1", "kick"), sample("2", "snare")] });

        const properties = lastPropertiesWith(latestInstance(), "pointColorActive");
        const palette = properties.pointColor as string[];
        expect(properties.pointColorActive).toEqual(palette.map(() => "#ffff00"));
        expect(properties.pointColorHover).toEqual(palette.map(() => "#ffffff"));
    });

    it("gives the substrate's slot its own opacity and every other slot the named points' one", async () => {
        document.documentElement.style.setProperty("--cloud-point-opacity", "0.8");
        document.documentElement.style.setProperty("--cloud-substrate-opacity", "0.3");
        await renderCloudView({ points: [sample("1", "kick"), sample("2", "uncategorized")] });

        const properties = lastPropertiesWith(latestInstance(), "opacity");
        const opacities = properties.opacity as number[];
        const substrateSlot = categoryIndex("uncategorized");
        expect(properties.opacityBy).toBe("category");
        expect(opacities[substrateSlot]).toBe(0.3);
        expect(opacities.filter((_, slot) => slot !== substrateSlot)).toEqual(
            Array.from({ length: opacities.length - 1 }, () => 0.8),
        );
    });

    it("draws the substrate's points beneath the named ones once the points are drawn", async () => {
        await renderCloudView({
            points: [
                sample("1", "kick"),
                sample("2", "uncategorized"),
                sample("3", "snare"),
                sample("4", "uncategorized"),
            ],
        });

        expect(latestInstance().set).toHaveBeenCalledWith({ pointOrder: [1, 3, 0, 2] });
    });

    it("draws a batch of one flat color in its own order", async () => {
        await renderCloudView({ points: [point(MODULE_REF, 0, 0)] });

        expect(latestInstance().set).toHaveBeenCalledWith({ pointOrder: null });
    });

    it("recreates the scatterplot when a theme changes the point shape, keeping its camera, points and highlight", async () => {
        const points = [sample("1", "kick"), sample("2", "snare")];
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
        await renderCloudView({ points: [sample("1", "kick")] });

        act(() => {
            useThemeStore.getState().setPreference("dark");
        });
        await flushDraw();

        expect(instances).toHaveLength(1);
    });
});
