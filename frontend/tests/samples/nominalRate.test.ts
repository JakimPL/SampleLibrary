import { describe, expect, it } from "vitest";

import { NOMINAL_WAV_RATE_HZ, playbackRateFor, soundedRate } from "../../src/samples/nominalRate";

describe("playbackRateFor", () => {
    it("returns 1 for the nominal WAV rate itself", () => {
        expect(playbackRateFor(NOMINAL_WAV_RATE_HZ)).toBe(1);
    });

    it("scales proportionally to the occurrence's real tracker rate", () => {
        expect(playbackRateFor(NOMINAL_WAV_RATE_HZ * 2)).toBe(2);
        expect(playbackRateFor(NOMINAL_WAV_RATE_HZ / 2)).toBe(0.5);
    });
});

describe("soundedRate", () => {
    it("runs a file stating its own rate as it stands", () => {
        expect(soundedRate(null)).toBe(1);
    });

    it("runs a stored file at the ratio between the library's rate and the file's own", () => {
        expect(soundedRate(8363)).toBeCloseTo(8363 / NOMINAL_WAV_RATE_HZ);
    });

    it("sounds a sample the library reads twice as fast at twice the speed", () => {
        expect(soundedRate(16726)).toBeCloseTo((8363 * 2) / NOMINAL_WAV_RATE_HZ);
    });
});
