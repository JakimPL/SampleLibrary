import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Thumbnail } from "../../src/samples/Thumbnail";

describe("Thumbnail", () => {
    it("shows a placeholder instead of a button when there is no cached thumbnail yet", () => {
        render(<Thumbnail pitch={null} sampleHash="sample-1" peaks={null} />);

        expect(screen.getByText("—")).toBeInTheDocument();
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it("renders a clickable canvas that plays the sample's audio", () => {
        render(<Thumbnail pitch={null} sampleHash="sample-thumbnail-play" peaks={[{ minimum: -1, maximum: 1 }]} />);

        const button = screen.getByRole("button", { name: "Play sample preview" });
        expect(button.querySelector("canvas")).toBeInTheDocument();

        fireEvent.click(button);

        expect(button).toHaveAttribute("aria-pressed", "true");
    });
});
