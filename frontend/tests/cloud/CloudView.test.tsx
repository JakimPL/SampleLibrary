import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CloudView } from "../../src/cloud/CloudView";
import type { CloudEntityPoint } from "../../src/cloud/geometry";
import type { EntityRef } from "../../src/workspace/selectionStore";

const { instances, createScatterplotMock } = vi.hoisted(() => {
    class FakeScatterplot {
        readonly draw = vi.fn().mockResolvedValue(undefined);
        readonly select = vi.fn();
        readonly deselect = vi.fn();
        readonly destroy = vi.fn();
        readonly getScreenPosition = vi.fn((index: number) => [10 + index, 20 + index] as [number, number]);
        private readonly listeners = new Map<string, ((payload: unknown) => void)[]>();

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
    const createScatterplotMock = vi.fn(() => {
        const instance = new FakeScatterplot();
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
}

function renderCloudView(overrides: RenderOverrides = {}): ReturnType<typeof render> {
    return render(
        <CloudView
            points={overrides.points ?? []}
            highlighted={overrides.highlighted ?? null}
            onSelect={overrides.onSelect ?? vi.fn()}
            onFocus={overrides.onFocus ?? vi.fn()}
            onClear={overrides.onClear ?? vi.fn()}
            onHover={overrides.onHover ?? vi.fn()}
        />,
    );
}

const SAMPLE_REF: EntityRef = { kind: "sample", hash: "a".repeat(64) };
const MODULE_REF: EntityRef = { kind: "module", hash: "b".repeat(64) };

beforeEach(() => {
    instances.length = 0;
    createScatterplotMock.mockClear();
});

describe("CloudView", () => {
    it("shows an honest empty state when there are no cloud coordinates yet", () => {
        renderCloudView();

        expect(screen.getByText("No cloud coordinates yet")).toBeInTheDocument();
    });

    it("draws every given point through the scatterplot", () => {
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)] });

        const drawnPoints = latestInstance().draw.mock.calls[0]?.[0] as unknown[];
        expect(drawnPoints).toHaveLength(1);
    });

    it("reports the entity behind a point the library reports as clicked", () => {
        const onSelect = vi.fn();
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onSelect });

        latestInstance().emit("select", { points: [0] });

        expect(onSelect).toHaveBeenCalledWith(SAMPLE_REF);
    });

    it("focuses the currently hovered entity on a native double-click", () => {
        const onFocus = vi.fn();
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onFocus });
        latestInstance().emit("pointOver", 0);

        fireEvent.dblClick(latestCanvas());

        expect(onFocus).toHaveBeenCalledWith(SAMPLE_REF);
    });

    it("does not focus anything on a double-click while the cursor is over no point", () => {
        const onFocus = vi.fn();
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onFocus });

        fireEvent.dblClick(latestCanvas());

        expect(onFocus).not.toHaveBeenCalled();
    });

    it("clears the highlight on a click that misses every point", () => {
        const onClear = vi.fn();
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onClear });

        fireEvent.click(latestCanvas());

        expect(onClear).toHaveBeenCalled();
    });

    it("does not clear the highlight on a click over a point", () => {
        const onClear = vi.fn();
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onClear });
        latestInstance().emit("pointOver", 0);

        fireEvent.click(latestCanvas());

        expect(onClear).not.toHaveBeenCalled();
    });

    it("clears the highlight when the library reports its own deselect (e.g. Escape)", () => {
        const onClear = vi.fn();
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onClear });

        latestInstance().emit("deselect");

        expect(onClear).toHaveBeenCalled();
    });

    it("selects the highlighted point within the scatterplot itself", () => {
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: SAMPLE_REF });

        expect(latestInstance().select).toHaveBeenCalledWith([0], { preventEvent: true });
    });

    it("deselects when the current highlight matches nothing on this view", () => {
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: MODULE_REF });

        expect(latestInstance().deselect).toHaveBeenCalledWith({ preventEvent: true });
    });

    it("destroys the scatterplot instance when the component unmounts", () => {
        const { unmount } = renderCloudView({ points: [point(SAMPLE_REF, 0, 0)] });
        const instance = latestInstance();

        unmount();

        expect(instance.destroy).toHaveBeenCalled();
    });

    it("reports the hovered entity and its screen position", () => {
        const onHover = vi.fn();
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onHover });

        latestInstance().emit("pointOver", 0);

        expect(onHover).toHaveBeenCalledWith(SAMPLE_REF, [10, 20]);
    });

    it("reports no hover once the cursor leaves the point", () => {
        const onHover = vi.fn();
        renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], onHover });
        latestInstance().emit("pointOver", 0);

        latestInstance().emit("pointOut");

        expect(onHover).toHaveBeenLastCalledWith(null, null);
    });

    it("shows a sonar ping at a newly highlighted point", () => {
        const { container } = renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: SAMPLE_REF });

        expect(container.querySelector(".cloud-ping")).toBeInTheDocument();
    });

    it("does not re-ping when the same highlight persists across a re-render", () => {
        const { container, rerender } = renderCloudView({
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
            />,
        );

        expect(container.querySelector(".cloud-ping")).toBe(firstPing);
    });

    it("does not re-ping when a value-equal but differently-referenced highlight is passed in", () => {
        const { container, rerender } = renderCloudView({
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
            />,
        );

        expect(container.querySelector(".cloud-ping")).toBe(firstPing);
    });

    it("keeps the ping pinned to its point through a pan or zoom", () => {
        const { container } = renderCloudView({ points: [point(SAMPLE_REF, 0, 0)], highlighted: SAMPLE_REF });
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
});
