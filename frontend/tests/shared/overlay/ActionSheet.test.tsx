import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ActionSheet } from "../../../src/shared/overlay/ActionSheet";

describe("ActionSheet", () => {
    it("runs the chosen action and closes, keeping a disabled one out of reach", () => {
        const run = vi.fn();
        const onClose = vi.fn();
        render(
            <ActionSheet
                title="kick"
                actions={[
                    { id: "play", label: "Play", disabled: false, run },
                    { id: "rest", label: "This is A", disabled: true, run: vi.fn() },
                ]}
                onClose={onClose}
            >
                <p>stars</p>
            </ActionSheet>,
        );

        expect(screen.getByRole("button", { name: "This is A" })).toBeDisabled();
        fireEvent.click(screen.getByRole("button", { name: "Play" }));

        expect(run).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
    });
});
