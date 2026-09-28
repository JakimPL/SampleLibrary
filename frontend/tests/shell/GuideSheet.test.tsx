import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useCurationAccess } from "../../src/samples/useCurationAccess";
import { GuideSheet } from "../../src/shell/GuideSheet";

describe("GuideSheet", () => {
    it("spells the gestures out for touch", () => {
        render(<GuideSheet input="touch" onClose={vi.fn()} />);

        expect(screen.getByRole("dialog", { name: "Gestures" })).toBeInTheDocument();
        expect(screen.getByText("Pinch")).toBeInTheDocument();
        expect(screen.getByText("A or B under the cloud")).toBeInTheDocument();
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

    it("leaves out the keys and gestures that change labels where they may only be seen", () => {
        vi.mocked(useCurationAccess).mockReturnValue({ curationShown: true, labelEditing: false });
        render(<GuideSheet input="pointer" onClose={vi.fn()} />);

        expect(screen.queryByText("1 to 5")).not.toBeInTheDocument();
        expect(screen.queryByText("F")).not.toBeInTheDocument();
        expect(screen.getByText("Space")).toBeInTheDocument();
    });

    it("says a held row opens its actions where labels may only be seen", () => {
        vi.mocked(useCurationAccess).mockReturnValue({ curationShown: true, labelEditing: false });
        render(<GuideSheet input="touch" onClose={vi.fn()} />);

        expect(screen.getAllByText("opens its actions")).toHaveLength(2);
        expect(screen.queryByText("opens its stars, heart and label")).not.toBeInTheDocument();
        expect(screen.queryByText("Tap the heart")).not.toBeInTheDocument();
    });
});
