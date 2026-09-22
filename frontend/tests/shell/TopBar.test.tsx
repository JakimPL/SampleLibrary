import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { TopBar } from "../../src/shell/TopBar";

describe("TopBar", () => {
    it("names the application as the way home, and offers the View menu and the theme", () => {
        render(
            <MemoryRouter>
                <TopBar api={null} />
            </MemoryRouter>,
        );

        expect(screen.getByRole("link", { name: "SampleLibrary" })).toHaveAttribute("href", "/");
        expect(screen.getByText("View")).toBeInTheDocument();
        expect(screen.getByLabelText("Theme")).toBeInTheDocument();
    });
});
