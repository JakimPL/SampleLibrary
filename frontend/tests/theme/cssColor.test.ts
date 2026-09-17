import { describe, expect, it } from "vitest";

import { colorWithAlpha, mixColors, parseCssColor, type Rgba } from "../../src/theme/cssColor";

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

/** One point on the path between two colors: where it stands, and what the result must hold. */
interface MixCase {
    readonly name: string;
    readonly weight: number;
    readonly expected: string;
}

const BLACK: Rgba = [0, 0, 0, 1];
const WHITE: Rgba = [1, 1, 1, 1];
const NAIVE_MIDPOINT_CHANNEL = 128;

const MIX_CASES: readonly MixCase[] = [
    { name: "returns the first color at the start of the path", weight: 0, expected: "rgb(0 0 0 / 1)" },
    { name: "returns the second color at the end of the path", weight: 1, expected: "rgb(255 255 255 / 1)" },
];

describe("mixColors", () => {
    it.each(MIX_CASES)("$name", ({ weight, expected }: MixCase) => {
        expect(mixColors(BLACK, WHITE, weight)).toBe(expected);
    });

    it("keeps the brightness of both colors halfway between them", () => {
        const halfway = mixColors(BLACK, WHITE, 0.5);

        const channel = Number(/rgb\((\d+)/.exec(halfway)?.[1]);
        expect(channel).toBeGreaterThan(NAIVE_MIDPOINT_CHANNEL);
    });

    it("carries the alpha of both ends along the path", () => {
        expect(mixColors([0, 0, 0, 0], [0, 0, 0, 1], 0.25)).toBe("rgb(0 0 0 / 0.25)");
    });
});

describe("colorWithAlpha", () => {
    it("keeps the color and stands it at the alpha asked for", () => {
        expect(colorWithAlpha([1, 0.5, 0, 1], 0.3)).toBe("rgb(255 128 0 / 0.3)");
    });

    it("leaves a color standing at full strength where that is what is asked for", () => {
        expect(colorWithAlpha(WHITE, 1)).toBe("rgb(255 255 255 / 1)");
    });
});
