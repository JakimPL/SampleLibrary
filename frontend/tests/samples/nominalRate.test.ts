import { describe, expect, it } from "vitest";

import { NOMINAL_WAV_RATE_HZ, playbackRateFor } from "../../src/samples/nominalRate";

describe("playbackRateFor", () => {
    it("returns 1 for the nominal WAV rate itself", () => {
        expect(playbackRateFor(NOMINAL_WAV_RATE_HZ)).toBe(1);
    });

    it("scales proportionally to the occurrence's real tracker rate", () => {
        expect(playbackRateFor(NOMINAL_WAV_RATE_HZ * 2)).toBe(2);
        expect(playbackRateFor(NOMINAL_WAV_RATE_HZ / 2)).toBe(0.5);
    });
});
