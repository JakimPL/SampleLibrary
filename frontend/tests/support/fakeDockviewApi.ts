import type { DockviewApi, SerializedDockview } from "dockview-react";
import { Orientation } from "dockview-react";
import { vi } from "vitest";

import type { PanelId } from "../../src/workspace/panelRegistry";

export interface FakePanel {
    readonly id: PanelId;
    readonly api: {
        readonly setActive: ReturnType<typeof vi.fn>;
        readonly close: ReturnType<typeof vi.fn>;
    };
}

function fakePanel(id: PanelId): FakePanel {
    return { id, api: { setActive: vi.fn(), close: vi.fn() } };
}

/** A serialized arrangement holding `ids` as the tabs of one group, the shape `toJSON` hands back. */
export function serializedLayoutOf(ids: readonly PanelId[]): SerializedDockview {
    const [first] = ids;
    return {
        grid: {
            root: {
                type: "leaf",
                data: { views: [...ids], ...(first === undefined ? {} : { activeView: first }), id: "group" },
            },
            width: 0,
            height: 0,
            orientation: Orientation.HORIZONTAL,
        },
        panels: Object.fromEntries(ids.map((id) => [id, { id, contentComponent: id, title: id }])),
    };
}

/**
 * The slice of `DockviewApi` the shell's own code reads: the open panels, layout events, and the
 * calls that add, restore and save an arrangement, each recorded.
 */
export class FakeDockviewApi {
    panels: FakePanel[];
    readonly addPanel = vi.fn();
    readonly fromJSON = vi.fn();
    readonly toJSON = vi.fn((): SerializedDockview => serializedLayoutOf(this.panels.map((panel) => panel.id)));
    private readonly listeners: (() => void)[] = [];

    constructor(openIds: readonly PanelId[]) {
        this.panels = openIds.map(fakePanel);
    }

    getPanel(id: string): FakePanel | undefined {
        return this.panels.find((panel) => panel.id === id);
    }

    onDidLayoutChange(listener: () => void): { dispose: () => void } {
        this.listeners.push(listener);
        return {
            dispose: (): void => {
                this.listeners.splice(this.listeners.indexOf(listener), 1);
            },
        };
    }

    emitLayoutChange(): void {
        for (const listener of [...this.listeners]) {
            listener();
        }
    }

    open(id: PanelId): void {
        this.panels.push(fakePanel(id));
    }

    asApi(): DockviewApi {
        return this as unknown as DockviewApi;
    }
}
