import { describe, expect, it } from "vitest";

import { parseCssColor } from "../../src/theme/cssColor";

describe("parseCssColor", () => {
    it.each([
        { text: "#fff", expected: [1, 1, 1, 1] },
        { text: "#00f8", expected: [0, 0, 1, 0x88 / 255] },
        { text: "#e0a845", expected: [0xe0 / 255, 0xa8 / 255, 0x45 / 255, 1] },
        { text: "#2e344080", expected: [0x2e / 255, 0x34 / 255, 0x40 / 255, 0x80 / 255] },
        { text: "  #FFFF00 ", expected: [1, 1, 0, 1] },
        { text: "rgb(255, 0, 0)", expected: [1, 0, 0, 1] },
        { text: "rgb(0 128 0 / 50%)", expected: [0, 128 / 255, 0, 0.5] },
        { text: "rgba(0, 0, 255, 0.25)", expected: [0, 0, 1, 0.25] },
    ])("reads $text", ({ text, expected }) => {
        const channels = parseCssColor(text);

        expect(channels).not.toBeNull();
        channels?.forEach((channel, index) => {
            expect(channel).toBeCloseTo(expected[index] ?? Number.NaN, 6);
        });
    });

    it.each(["", "white", "#12", "#12345", "hsl(0 100% 50%)", "rgb(1, 2)"])("answers null for %j", (text) => {
        expect(parseCssColor(text)).toBeNull();
    });
});
