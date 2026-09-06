import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { DockviewApi } from "dockview-react";
import { describe, expect, it, vi } from "vitest";

import { AddPanelMenu } from "../../src/workspace/AddPanelMenu";
import type { PanelId } from "../../src/workspace/panelRegistry";

const ALL_PANEL_IDS: readonly PanelId[] = [
    "modules-list",
    "samples-list",
    "cloud",
    "waveform",
    "module-detail",
    "sample-detail",
    "stats",
];

interface FakePanel {
    readonly id: PanelId;
}

/**
 * A minimal stand-in for `DockviewApi`, covering only the surface `AddPanelMenu` reads --
 * `panels`, `onDidLayoutChange`, and `addPanel` -- rather than the whole real class.
 */
class FakeDockviewApi {
    panels: FakePanel[];
    readonly addPanel = vi.fn();
    private readonly listeners: (() => void)[] = [];

    constructor(openIds: readonly PanelId[]) {
        this.panels = openIds.map((id) => ({ id }));
    }

    onDidLayoutChange(listener: () => void): { dispose: () => void } {
        this.listeners.push(listener);
        return { dispose: () => undefined };
    }

    emitLayoutChange(): void {
        for (const listener of this.listeners) {
            listener();
        }
    }
}

function fakeApi(openIds: readonly PanelId[]): FakeDockviewApi {
    return new FakeDockviewApi(openIds);
}

const OPEN_EXCEPT_STATS: readonly PanelId[] = ALL_PANEL_IDS.filter((id) => id !== "stats");

describe("AddPanelMenu", () => {
    it("renders nothing before the dockview api is ready", () => {
        const { container } = render(<AddPanelMenu api={null} />);

        expect(container).toBeEmptyDOMElement();
    });

    it("renders nothing once every registered panel is already open", () => {
        const api = fakeApi(ALL_PANEL_IDS);

        const { container } = render(<AddPanelMenu api={api as unknown as DockviewApi} />);

        expect(container).toBeEmptyDOMElement();
    });

    it("lists only the panels not currently open", () => {
        const api = fakeApi(OPEN_EXCEPT_STATS);

        render(<AddPanelMenu api={api as unknown as DockviewApi} />);

        expect(screen.getByRole("button", { name: "Stats" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Modules" })).not.toBeInTheDocument();
    });

    it("adds the chosen panel back through the dockview api", () => {
        const api = fakeApi(OPEN_EXCEPT_STATS);
        render(<AddPanelMenu api={api as unknown as DockviewApi} />);

        fireEvent.click(screen.getByRole("button", { name: "Stats" }));

        expect(api.addPanel).toHaveBeenCalledWith({ id: "stats", component: "stats", title: "Stats" });
    });

    it("drops a panel from the menu once the layout reports it open", async () => {
        const api = fakeApi(OPEN_EXCEPT_STATS);
        render(<AddPanelMenu api={api as unknown as DockviewApi} />);
        expect(screen.getByRole("button", { name: "Stats" })).toBeInTheDocument();

        api.panels.push({ id: "stats" });
        act(() => {
            api.emitLayoutChange();
        });

        await waitFor(() => {
            expect(screen.queryByRole("button", { name: "Stats" })).not.toBeInTheDocument();
        });
    });
});
