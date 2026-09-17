import { describe, expect, it } from "vitest";

import { heardSeconds, NOMINAL_WAV_RATE_HZ, playbackRateFor, soundedRate } from "../../src/samples/nominalRate";

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

/** One stored file against the speed the library runs it at, and the length it then really sounds. */
interface HeardCase {
    readonly name: string;
    readonly storedSeconds: number;
    readonly playbackRateHz: number | null;
    readonly seconds: number;
}

const HEARD_CASES: readonly HeardCase[] = [
    {
        name: "lasts as long as it is stored when the file states its own rate",
        storedSeconds: 1.5,
        playbackRateHz: null,
        seconds: 1.5,
    },
    {
        name: "lasts as long as it is stored when the library reads it at the nominal rate",
        storedSeconds: 1.5,
        playbackRateHz: NOMINAL_WAV_RATE_HZ,
        seconds: 1.5,
    },
    {
        name: "lasts twice as long when the library reads it half as fast",
        storedSeconds: 1.5,
        playbackRateHz: NOMINAL_WAV_RATE_HZ / 2,
        seconds: 3,
    },
    {
        name: "lasts half as long when the library reads it twice as fast",
        storedSeconds: 1.5,
        playbackRateHz: NOMINAL_WAV_RATE_HZ * 2,
        seconds: 0.75,
    },
];

describe("heardSeconds", () => {
    it.each(HEARD_CASES)("$name", ({ storedSeconds, playbackRateHz, seconds }: HeardCase) => {
        expect(heardSeconds(storedSeconds, playbackRateHz)).toBeCloseTo(seconds);
    });
});
