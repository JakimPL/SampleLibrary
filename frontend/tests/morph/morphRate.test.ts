import { describe, expect, it } from "vitest";

import { morphPlaybackRateHz, rateBetween } from "../../src/morph/morphRate";

const FIRST_RATE_HZ = 8363;
const SECOND_RATE_HZ = 16726;

describe("rateBetween", () => {
    it("runs from the first rate to the second through their pitches", () => {
        expect(rateBetween(FIRST_RATE_HZ, SECOND_RATE_HZ, 0)).toBeCloseTo(FIRST_RATE_HZ);
        expect(rateBetween(FIRST_RATE_HZ, SECOND_RATE_HZ, 1)).toBeCloseTo(SECOND_RATE_HZ);
        expect(rateBetween(FIRST_RATE_HZ, SECOND_RATE_HZ, 0.5)).toBeCloseTo(FIRST_RATE_HZ * Math.SQRT2);
    });
});

describe("morphPlaybackRateHz", () => {
    it("is unknown as soon as either end's rate is", () => {
        expect(morphPlaybackRateHz(null, SECOND_RATE_HZ, 0.5)).toBeNull();
        expect(morphPlaybackRateHz(FIRST_RATE_HZ, null, 0.5)).toBeNull();
        expect(morphPlaybackRateHz(FIRST_RATE_HZ, SECOND_RATE_HZ, 0.5)).toBeCloseTo(FIRST_RATE_HZ * Math.SQRT2);
    });
});
