import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlayButton } from "../../src/samples/PlayButton";

describe("PlayButton", () => {
    it("renders its children inside a clickable button that plays the sample's audio", () => {
        render(<PlayButton sampleHash="sample-play-button">▶</PlayButton>);

        const button = screen.getByRole("button", { name: "Play sample preview" });
        expect(button).toHaveTextContent("▶");

        fireEvent.click(button);

        expect(button).toHaveAttribute("aria-pressed", "true");
    });

    it("is not pressed for a sample other than the one currently playing", () => {
        render(<PlayButton sampleHash="sample-not-playing">▶</PlayButton>);

        expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "false");
    });
});
