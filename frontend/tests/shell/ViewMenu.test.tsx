import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePlayerStripStore } from "../../src/shell/player/playerStripStore";
import { ViewMenu } from "../../src/shell/ViewMenu";
import { defaultSerializedLayout } from "../../src/workspace/defaultLayout";
import { PANEL_REGISTRY, type PanelId } from "../../src/workspace/panelRegistry";
import { FakeDockviewApi } from "../support/fakeDockviewApi";

const ALL_PANEL_IDS = Object.keys(PANEL_REGISTRY) as PanelId[];
const OPEN_EXCEPT_STATS = ALL_PANEL_IDS.filter((id) => id !== "stats");

function openMenu(): void {
    fireEvent.click(screen.getByText("View"));
}

describe("ViewMenu", () => {
    it("lists every registered panel, ticked when it is open", () => {
        const api = new FakeDockviewApi(OPEN_EXCEPT_STATS);
        render(<ViewMenu api={api.asApi()} />);
        openMenu();

        expect(screen.getByRole("checkbox", { name: "Stats" })).not.toBeChecked();
        expect(screen.getByRole("checkbox", { name: "Cloud" })).toBeChecked();
        expect(screen.getAllByRole("checkbox")).toHaveLength(ALL_PANEL_IDS.length + 1);
    });

    it("waits, disabled, until the dockview api is ready", () => {
        render(<ViewMenu api={null} />);
        openMenu();

        expect(screen.getByRole("checkbox", { name: "Stats" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Reset layout" })).toBeDisabled();
    });

    it("reopens a closed panel at its registered placement when the reference is open", () => {
        const api = new FakeDockviewApi(OPEN_EXCEPT_STATS);
        render(<ViewMenu api={api.asApi()} />);
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
        render(<ViewMenu api={api.asApi()} />);
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
        render(<ViewMenu api={api.asApi()} />);
        openMenu();

        fireEvent.click(screen.getByRole("checkbox", { name: "Cloud" }));

        expect(api.getPanel("cloud")?.api.close).toHaveBeenCalled();
    });

    it("ticks a panel once the layout reports it open", async () => {
        const api = new FakeDockviewApi(OPEN_EXCEPT_STATS);
        render(<ViewMenu api={api.asApi()} />);
        openMenu();

        api.open("stats");
        act(() => {
            api.emitLayoutChange();
        });

        await waitFor(() => {
            expect(screen.getByRole("checkbox", { name: "Stats" })).toBeChecked();
        });
    });

    it("switches the player strip on and off", () => {
        const api = new FakeDockviewApi(ALL_PANEL_IDS);
        render(<ViewMenu api={api.asApi()} />);
        openMenu();
        const before = usePlayerStripStore.getState().visible;

        fireEvent.click(screen.getByRole("checkbox", { name: "Player strip" }));

        expect(usePlayerStripStore.getState().visible).toBe(!before);
        fireEvent.click(screen.getByRole("checkbox", { name: "Player strip" }));
        expect(usePlayerStripStore.getState().visible).toBe(before);
    });

    it("draws the first-run arrangement again on reset", () => {
        const api = new FakeDockviewApi(ALL_PANEL_IDS);
        render(<ViewMenu api={api.asApi()} />);
        openMenu();

        fireEvent.click(screen.getByRole("button", { name: "Reset layout" }));

        expect(api.fromJSON).toHaveBeenCalledWith(defaultSerializedLayout());
    });
});
