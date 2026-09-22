import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BottomSheet } from "../../../src/shared/overlay/BottomSheet";

describe("BottomSheet", () => {
    it("shows a dialog named by its title at the document's root", () => {
        render(
            <div id="host">
                <BottomSheet title="Label" onClose={vi.fn()}>
                    <p>inside</p>
                </BottomSheet>
            </div>,
        );

        const dialog = screen.getByRole("dialog", { name: "Label" });
        expect(dialog).toHaveTextContent("inside");
        expect(dialog.closest("#host")).toBeNull();
        expect(dialog).toHaveFocus();
    });

    it("closes from the scrim and from Escape", () => {
        const onClose = vi.fn();
        render(
            <BottomSheet title="Label" onClose={onClose}>
                <p>inside</p>
            </BottomSheet>,
        );

        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        fireEvent.keyDown(document, { key: "Escape" });

        expect(onClose).toHaveBeenCalledTimes(2);
    });

    it("hands the focus back to the control that opened it", () => {
        const opener = document.createElement("button");
        document.body.append(opener);
        opener.focus();
        const { unmount } = render(
            <BottomSheet title="Label" onClose={vi.fn()}>
                <p>inside</p>
            </BottomSheet>,
        );
        expect(opener).not.toHaveFocus();

        unmount();

        expect(opener).toHaveFocus();
        opener.remove();
    });
});
