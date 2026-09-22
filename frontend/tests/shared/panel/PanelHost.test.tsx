import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PanelHost } from "../../../src/shared/panel/PanelHost";

describe("PanelHost", () => {
    it("wraps a panel in the box its rules query, named by the panel", () => {
        render(
            <PanelHost panelId="cloud">
                <p>points</p>
            </PanelHost>,
        );

        const host = screen.getByText("points").parentElement;
        expect(host).toHaveClass("panel-host");
        expect(host).toHaveAttribute("data-panel", "cloud");
    });
});
