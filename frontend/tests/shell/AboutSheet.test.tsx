import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AboutSheet } from "../../src/shell/AboutSheet";
import { APP_VERSION } from "../../src/version";

describe("AboutSheet", () => {
    it("names the app, its version, its maker and the way to its source", () => {
        render(<AboutSheet onClose={() => undefined} />);

        expect(screen.getByRole("dialog", { name: "About" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "SampleRipper" })).toBeInTheDocument();
        expect(screen.getByText(`Version ${APP_VERSION}`)).toBeInTheDocument();
        expect(screen.getByText("Made by Jakim / Stage Magician")).toBeInTheDocument();
        expect(document.querySelector("img.about-logo")).toHaveAttribute("alt", "");
    });

    it("opens the source in a new tab that learns nothing of this page", () => {
        render(<AboutSheet onClose={() => undefined} />);

        const link = screen.getByRole("link", { name: "Source on GitHub" });

        expect(link).toHaveAttribute("href", "https://github.com/JakimPL/SampleRipper");
        expect(link).toHaveAttribute("target", "_blank");
        expect(link.getAttribute("rel")).toContain("noreferrer");
    });

    it("closes from the scrim", () => {
        const onClose = vi.fn();
        render(<AboutSheet onClose={onClose} />);

        fireEvent.click(screen.getByRole("button", { name: "Close" }));

        expect(onClose).toHaveBeenCalledOnce();
    });
});
