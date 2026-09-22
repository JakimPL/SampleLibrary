import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PanelToolbar, TOOLBAR_COLLAPSE_WIDTH_PX } from "../../../src/shared/panel/PanelToolbar";

function rectOfWidth(width: number): DOMRect {
    return { x: 0, y: 0, width, height: 30, top: 0, right: width, bottom: 30, left: 0, toJSON: () => ({}) };
}

function renderToolbar(width: number): void {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(rectOfWidth(width));
    render(
        <PanelToolbar
            primary={<input aria-label="Filter" />}
            secondary={<button type="button">Favorites</button>}
            status={<span>3 of 40 loaded</span>}
        />,
    );
}

describe("PanelToolbar", () => {
    it("lays the controls side by side at full width", () => {
        renderToolbar(TOOLBAR_COLLAPSE_WIDTH_PX);

        expect(screen.getByRole("button", { name: "Favorites" })).toBeVisible();
        expect(screen.queryByText("Filters")).not.toBeInTheDocument();
        expect(screen.getByText("3 of 40 loaded")).toBeInTheDocument();
    });

    it("folds the secondary controls into a menu in a narrow panel", () => {
        renderToolbar(TOOLBAR_COLLAPSE_WIDTH_PX - 1);

        expect(screen.getByLabelText("Filter")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Favorites" })).not.toBeVisible();

        fireEvent.click(screen.getByText("Filters"));

        expect(screen.getByRole("button", { name: "Favorites" })).toBeVisible();
    });
});
