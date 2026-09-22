import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DisclosureMenu } from "../../../src/shared/overlay/DisclosureMenu";

function renderMenu(): HTMLElement {
    render(
        <div>
            <p>outside</p>
            <DisclosureMenu label="View" className="test-menu">
                <p>inside</p>
            </DisclosureMenu>
        </div>,
    );
    return screen.getByText("View").closest("details") as HTMLElement;
}

describe("DisclosureMenu", () => {
    it("starts closed and opens on a click of its label", () => {
        const details = renderMenu();
        expect(details).not.toHaveAttribute("open");

        fireEvent.click(screen.getByText("View"));

        expect(details).toHaveAttribute("open");
    });

    it("closes on a second click, on Escape, and on a press outside", () => {
        const details = renderMenu();
        const label = screen.getByText("View");

        fireEvent.click(label);
        fireEvent.click(label);
        expect(details).not.toHaveAttribute("open");

        fireEvent.click(label);
        fireEvent.keyDown(document, { key: "Escape" });
        expect(details).not.toHaveAttribute("open");

        fireEvent.click(label);
        fireEvent.pointerDown(screen.getByText("outside"));
        expect(details).not.toHaveAttribute("open");
    });

    it("stays open on a press inside", () => {
        const details = renderMenu();
        fireEvent.click(screen.getByText("View"));

        fireEvent.pointerDown(screen.getByText("inside"));

        expect(details).toHaveAttribute("open");
    });
});
