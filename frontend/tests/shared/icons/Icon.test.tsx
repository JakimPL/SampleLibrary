import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Icon } from "../../../src/shared/icons/Icon";
import { ICON_PATHS } from "../../../src/shared/icons/iconPaths";

describe("Icon", () => {
    it("draws the named path as an image with its label", () => {
        render(<Icon name="cloud" label="Cloud" />);

        const icon = screen.getByRole("img", { name: "Cloud" });
        expect(icon.querySelector("path")).toHaveAttribute("d", ICON_PATHS.cloud);
    });

    it("hides a decorative icon from assistive technology", () => {
        const { container } = render(<Icon name="stats" label={null} />);

        expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
        expect(screen.queryByRole("img")).not.toBeInTheDocument();
    });
});
