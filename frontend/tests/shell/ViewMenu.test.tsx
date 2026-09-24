import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { DockviewApi } from "dockview-react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ViewMenu } from "../../src/shell/ViewMenu";
import { defaultSerializedLayout } from "../../src/workspace/defaultLayout";
import { PANEL_REGISTRY, type PanelId } from "../../src/workspace/panelRegistry";
import { FakeDockviewApi } from "../support/fakeDockviewApi";

function renderMenu(api: DockviewApi | null): void {
    render(
        <MemoryRouter>
            <ViewMenu api={api} />
        </MemoryRouter>,
    );
}

const ALL_PANEL_IDS = Object.keys(PANEL_REGISTRY) as PanelId[];
const OPEN_EXCEPT_STATS = ALL_PANEL_IDS.filter((id) => id !== "stats");

function openMenu(): void {
    fireEvent.click(screen.getByText("View"));
}

describe("ViewMenu", () => {
    it("opens the guide to the keys and clicks", () => {
        renderMenu(null);
        openMenu();

        fireEvent.click(screen.getByRole("button", { name: "Keyboard and mouse" }));

        expect(screen.getByRole("dialog", { name: "Keyboard and mouse" })).toBeInTheDocument();
        expect(screen.getByText("Shift-click")).toBeInTheDocument();
    });

    it("opens the diagnostics", () => {
        renderMenu(null);
        openMenu();

        fireEvent.click(screen.getByRole("button", { name: "Diagnostics" }));

        expect(screen.getByRole("dialog", { name: "Diagnostics" })).toBeInTheDocument();
        expect(screen.getByRole("radio", { name: "Plain dots" })).toBeInTheDocument();
    });

    it("lists every registered panel, ticked when it is open", () => {
        const api = new FakeDockviewApi(OPEN_EXCEPT_STATS);
        renderMenu(api.asApi());
        openMenu();

        expect(screen.getByRole("checkbox", { name: "Stats" })).not.toBeChecked();
        expect(screen.getByRole("checkbox", { name: "Cloud" })).toBeChecked();
        expect(screen.getAllByRole("checkbox")).toHaveLength(ALL_PANEL_IDS.length);
    });

    it("waits, disabled, until the dockview api is ready", () => {
        renderMenu(null);
        openMenu();

        expect(screen.getByRole("checkbox", { name: "Stats" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Reset layout" })).toBeDisabled();
    });

    it("reopens a closed panel at its registered placement when the reference is open", () => {
        const api = new FakeDockviewApi(OPEN_EXCEPT_STATS);
        renderMenu(api.asApi());
        openMenu();

        fireEvent.click(screen.getByRole("checkbox", { name: "Stats" }));

        expect(api.addPanel).toHaveBeenCalledWith({
            id: "stats",
            component: "stats",
            title: "Stats",
            renderer: "onlyWhenVisible",
            position: { direction: "within", referencePanel: "sample-detail" },
        });
    });

    it("falls back to no preferred placement when the reference panel is also closed", () => {
        const api = new FakeDockviewApi(ALL_PANEL_IDS.filter((id) => id !== "stats" && id !== "sample-detail"));
        renderMenu(api.asApi());
        openMenu();

        fireEvent.click(screen.getByRole("checkbox", { name: "Stats" }));

        expect(api.addPanel).toHaveBeenCalledWith({
            id: "stats",
            component: "stats",
            title: "Stats",
            renderer: "onlyWhenVisible",
        });
    });

    it("closes an open panel through its own api", () => {
        const api = new FakeDockviewApi(ALL_PANEL_IDS);
        renderMenu(api.asApi());
        openMenu();

        fireEvent.click(screen.getByRole("checkbox", { name: "Cloud" }));

        expect(api.getPanel("cloud")?.api.close).toHaveBeenCalled();
    });

    it("ticks a panel once the layout reports it open", async () => {
        const api = new FakeDockviewApi(OPEN_EXCEPT_STATS);
        renderMenu(api.asApi());
        openMenu();

        api.open("stats");
        act(() => {
            api.emitLayoutChange();
        });

        await waitFor(() => {
            expect(screen.getByRole("checkbox", { name: "Stats" })).toBeChecked();
        });
    });

    it("draws the first-run arrangement again on reset", () => {
        const api = new FakeDockviewApi(ALL_PANEL_IDS);
        renderMenu(api.asApi());
        openMenu();

        fireEvent.click(screen.getByRole("button", { name: "Reset layout" }));

        expect(api.fromJSON).toHaveBeenCalledWith(defaultSerializedLayout());
    });
});
