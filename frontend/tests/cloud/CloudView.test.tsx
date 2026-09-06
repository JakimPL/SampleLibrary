import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CloudView } from "../../src/cloud/CloudView";
import type { CloudEntityPoint } from "../../src/cloud/geometry";
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

function point(ref: EntityRef, x: number, y: number): CloudEntityPoint {
    return { ref, x, y };
}

interface RenderOverrides {
    readonly points?: readonly CloudEntityPoint[];
    readonly highlighted?: EntityRef | null;
    readonly onSelect?: (entity: EntityRef) => void;
    readonly onFocus?: (entity: EntityRef) => void;
    readonly onClear?: () => void;
    readonly onHover?: (entity: EntityRef | null, screenPosition: readonly [number, number] | null) => void;
    readonly onCompare?: (entity: EntityRef) => void;
}

// CloudView awaits the fake scatterplot's `draw` promise (mirroring the real library, which
// throws from `getScreenPosition` until a first draw resolves) before selecting or deselecting,
// so every render or rerender needs one microtask flush before its result is observable.
async function flushDraw(): Promise<void> {
    await act(async () => {
        await Promise.resolve();
    });
}

async function renderCloudView(overrides: RenderOverrides = {}): Promise<ReturnType<typeof render>> {
    const result = render(
        <CloudView
            points={overrides.points ?? []}
            highlighted={overrides.highlighted ?? null}
            onSelect={overrides.onSelect ?? vi.fn()}
            onFocus={overrides.onFocus ?? vi.fn()}
            onClear={overrides.onClear ?? vi.fn()}
            onHover={overrides.onHover ?? vi.fn()}
            onCompare={overrides.onCompare ?? vi.fn()}
        />,
    );
    await flushDraw();
    return result;
}

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

    it("reports a Shift-clicked point as a comparison target", async () => {
        const onCompare = vi.fn();
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onCompare });
        latestInstance().emit("pointOver", 0);

        fireEvent.click(latestCanvas(), { shiftKey: true });

        expect(onCompare).toHaveBeenCalledWith(SAMPLE_REF);
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

    it("selects the highlighted point within the scatterplot itself", async () => {
        await renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: SAMPLE_REF });

        expect(latestInstance().select).toHaveBeenCalledWith([0], { preventEvent: true });
    });

    // Regression test for a real crash: regl-scatterplot throws "Points have not been drawn" from
    // `getScreenPosition` (and a caller reading it right after `select`) until a first `draw` call
    // resolves. Calling `select` synchronously, right after firing `draw` without awaiting it,
    // reproduced this reliably on a fresh mount -- reopening the Cloud panel while a sample was
    // already highlighted crashed the whole app with exactly this error.
    it("waits for the scatterplot's draw to resolve before selecting the highlighted point", async () => {
        render(
            <CloudView
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onCompare={vi.fn()}
            />,
        );

        expect(latestInstance().select).not.toHaveBeenCalled();

        await flushDraw();

        expect(latestInstance().select).toHaveBeenCalledWith([0], { preventEvent: true });
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
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onCompare={vi.fn()}
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
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={{ kind: SAMPLE_REF.kind, hash: SAMPLE_REF.hash }}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
                onClear={vi.fn()}
                onHover={vi.fn()}
                onCompare={vi.fn()}
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
});
