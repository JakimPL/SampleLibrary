import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HelpMenu } from "../../src/shell/HelpMenu";

function openMenu(): void {
    render(<HelpMenu />);
    fireEvent.click(screen.getByText("Help"));
}

describe("HelpMenu", () => {
    it("opens the guide to the keys and clicks", () => {
        openMenu();

        fireEvent.click(screen.getByRole("button", { name: "Keyboard and mouse" }));

        expect(screen.getByRole("dialog", { name: "Keyboard and mouse" })).toBeInTheDocument();
        expect(screen.getByText("Shift-click")).toBeInTheDocument();
    });

    it("opens the diagnostics", () => {
        openMenu();

        fireEvent.click(screen.getByRole("button", { name: "Diagnostics" }));

        expect(screen.getByRole("dialog", { name: "Diagnostics" })).toBeInTheDocument();
        expect(screen.getByRole("radio", { name: "Plain dots" })).toBeInTheDocument();
    });

    it("opens About", () => {
        openMenu();

        fireEvent.click(screen.getByRole("button", { name: "About" }));

        expect(screen.getByRole("dialog", { name: "About" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Source on GitHub" })).toBeInTheDocument();
    });
});
