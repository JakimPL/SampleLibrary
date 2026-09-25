import { describe, expect, it } from "vitest";

import type { ProgressReport } from "../../src/api/setup";
import {
    describeElapsed,
    describeEstimate,
    ESTIMATE_WARMUP_SECONDS,
    estimateRemainingSeconds,
} from "../../src/setup/timing";

const STARTED_AT = "2026-09-24T10:00:00Z";

function reportAfter(seconds: number, done: number, total: number): ProgressReport {
    return {
        label: "Counting",
        done,
        total,
        started_at: STARTED_AT,
        updated_at: new Date(Date.parse(STARTED_AT) + seconds * 1000).toISOString(),
    };
}

describe("estimateRemainingSeconds", () => {
    it("carries the pace kept so far over the items left", () => {
        expect(estimateRemainingSeconds(reportAfter(60, 100, 400))).toBe(180);
    });

    it("waits for the pass to settle and stops once every item is done", () => {
        expect(estimateRemainingSeconds(reportAfter(ESTIMATE_WARMUP_SECONDS - 1, 100, 400))).toBeNull();
        expect(estimateRemainingSeconds(reportAfter(60, 0, 400))).toBeNull();
        expect(estimateRemainingSeconds(reportAfter(60, 400, 400))).toBeNull();
    });
});

describe("describeEstimate", () => {
    it.each([
        [45, "less than a minute left"],
        [150, "about 3 min left"],
        [23 * 60, "about 25 min left"],
        [58 * 60, "about 1 h left"],
        [134 * 60, "about 2 h 10 min left"],
    ])("rounds %d seconds to %s", (seconds, text) => {
        expect(describeEstimate(seconds)).toBe(text);
    });
});

describe("describeElapsed", () => {
    it.each([
        [-2, "0 s"],
        [45.7, "45 s"],
        [12 * 60 + 59, "12 min"],
        [65 * 60, "1 h 5 min"],
        [120 * 60, "2 h"],
    ])("reads %d seconds as %s", (seconds, text) => {
        expect(describeElapsed(seconds)).toBe(text);
    });
});
