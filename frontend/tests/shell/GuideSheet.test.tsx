import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GuideSheet } from "../../src/shell/GuideSheet";

describe("GuideSheet", () => {
    it("spells the gestures out for touch", () => {
        render(<GuideSheet input="touch" onClose={vi.fn()} />);

        expect(screen.getByRole("dialog", { name: "Gestures" })).toBeInTheDocument();
        expect(screen.getByText("Pinch")).toBeInTheDocument();
        expect(screen.queryByText("Shift-click")).not.toBeInTheDocument();
    });

    it("spells the keys and clicks out for a pointer, and closes from its scrim", () => {
        const onClose = vi.fn();
        render(<GuideSheet input="pointer" onClose={onClose} />);

        expect(screen.getByRole("dialog", { name: "Keyboard and mouse" })).toBeInTheDocument();
        expect(screen.getByText("Alt+← Alt+→")).toBeInTheDocument();
        expect(screen.queryByText("Pinch")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        expect(onClose).toHaveBeenCalled();
    });
});
