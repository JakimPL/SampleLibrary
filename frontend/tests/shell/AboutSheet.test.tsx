import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AboutSheet } from "../../src/shell/AboutSheet";
import { BUILD_VERSION } from "../../src/version";

describe("AboutSheet", () => {
    it("names the app and the version it was built with, under a decorative logo", () => {
        render(<AboutSheet onClose={() => undefined} />);

        expect(screen.getByRole("dialog")).toBeInTheDocument();
        expect(screen.getByRole("heading", { level: 3 })).toBeInTheDocument();
        expect(screen.getByText(BUILD_VERSION, { exact: false })).toBeInTheDocument();
        expect(document.querySelector("img.about-logo")).toHaveAttribute("alt", "");
    });

    it("opens every link in a new tab that learns nothing of this page", () => {
        render(<AboutSheet onClose={() => undefined} />);

        const links = screen.getAllByRole("link");

        expect(links.length).toBeGreaterThan(0);
        for (const link of links) {
            expect(link.getAttribute("href")).toMatch(/^https:\/\//);
            expect(link).toHaveAttribute("target", "_blank");
            expect(link.getAttribute("rel")).toContain("noreferrer");
        }
    });

    it("closes from the scrim", () => {
        const onClose = vi.fn();
        render(<AboutSheet onClose={onClose} />);

        fireEvent.click(screen.getByRole("button", { name: "Close" }));

        expect(onClose).toHaveBeenCalledOnce();
    });
});
