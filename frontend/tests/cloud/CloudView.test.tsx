import { fireEvent, render, screen } from "@testing-library/react";
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

const SAMPLE_REF: EntityRef = { kind: "sample", hash: "a".repeat(64) };
const MODULE_REF: EntityRef = { kind: "module", hash: "b".repeat(64) };

beforeEach(() => {
    instances.length = 0;
    createScatterplotMock.mockClear();
});

describe("CloudView", () => {
    it("shows an honest empty state when there are no cloud coordinates yet", () => {
        render(<CloudView points={[]} highlighted={null} onSelect={vi.fn()} onFocus={vi.fn()} />);

        expect(screen.getByText("No cloud coordinates yet")).toBeInTheDocument();
    });

    it("draws every given point through the scatterplot", () => {
        render(
            <CloudView points={[point(SAMPLE_REF, 0, 0)]} highlighted={null} onSelect={vi.fn()} onFocus={vi.fn()} />,
        );

        const drawnPoints = latestInstance().draw.mock.calls[0]?.[0] as unknown[];
        expect(drawnPoints).toHaveLength(1);
    });

    it("reports the entity behind a point the library reports as clicked", () => {
        const onSelect = vi.fn();
        render(
            <CloudView points={[point(SAMPLE_REF, 0, 0)]} highlighted={null} onSelect={onSelect} onFocus={vi.fn()} />,
        );

        latestInstance().emit("select", { points: [0] });

        expect(onSelect).toHaveBeenCalledWith(SAMPLE_REF);
    });

    it("focuses the currently hovered entity on a native double-click", () => {
        const onFocus = vi.fn();
        render(
            <CloudView points={[point(SAMPLE_REF, 0, 0)]} highlighted={null} onSelect={vi.fn()} onFocus={onFocus} />,
        );
        latestInstance().emit("pointOver", 0);

        fireEvent.dblClick(latestCanvas());

        expect(onFocus).toHaveBeenCalledWith(SAMPLE_REF);
    });

    it("does not focus anything on a double-click while the cursor is over no point", () => {
        const onFocus = vi.fn();
        render(
            <CloudView points={[point(SAMPLE_REF, 0, 0)]} highlighted={null} onSelect={vi.fn()} onFocus={onFocus} />,
        );

        fireEvent.dblClick(latestCanvas());

        expect(onFocus).not.toHaveBeenCalled();
    });

    it("selects the highlighted point within the scatterplot itself", () => {
        render(
            <CloudView
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={SAMPLE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
            />,
        );

        expect(latestInstance().select).toHaveBeenCalledWith([0], { preventEvent: true });
    });

    it("deselects when the current highlight matches nothing on this view", () => {
        render(
            <CloudView
                points={[point(SAMPLE_REF, 0, 0)]}
                highlighted={MODULE_REF}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
            />,
        );

        expect(latestInstance().deselect).toHaveBeenCalledWith({ preventEvent: true });
    });

    it("destroys the scatterplot instance when the component unmounts", () => {
        const { unmount } = render(
            <CloudView points={[point(SAMPLE_REF, 0, 0)]} highlighted={null} onSelect={vi.fn()} onFocus={vi.fn()} />,
        );
        const instance = latestInstance();

        unmount();

        expect(instance.destroy).toHaveBeenCalled();
    });
});
