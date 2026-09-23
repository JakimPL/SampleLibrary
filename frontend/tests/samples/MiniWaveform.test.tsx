import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MiniWaveform } from "../../src/samples/MiniWaveform";
import { stubDevicePixelRatio } from "../support/devicePixelRatio";

const PEAKS = [
    { minimum: -1, maximum: 1 },
    { minimum: -0.5, maximum: 0.5 },
];

describe("MiniWaveform", () => {
    it("backs its canvas with the box the stylesheet gives it, at the screen's density", () => {
        stubDevicePixelRatio(2);
        vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValueOnce({
            x: 0,
            y: 0,
            width: 174,
            height: 51,
            top: 0,
            right: 174,
            bottom: 51,
            left: 0,
            toJSON: () => ({}),
        });

        const { container } = render(<MiniWaveform peaks={PEAKS} />);

        expect(container.querySelector(".mini-waveform")).toBeInTheDocument();
        expect(container.querySelector("canvas")).toHaveAttribute("width", "348");
        expect(container.querySelector("canvas")).toHaveAttribute("height", "102");
    });
});
