import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { normalized, peaksFrom, useAudioPeaks } from "../../src/samples/audioPeaks";

const REFUSAL = "the two ends are heard 9.2 times apart in rate, and a morph spans at most 4";

/** One waveform reduced to buckets: what it holds, how many are asked for, and the extremes each one reaches. */
interface PeaksCase {
    readonly name: string;
    readonly samples: readonly number[];
    readonly bucketCount: number;
    readonly expected: readonly { readonly minimum: number; readonly maximum: number }[];
}

const PEAKS_CASES: readonly PeaksCase[] = [
    {
        name: "reaches the extremes of each equal span of the waveform",
        samples: [0, 1, 0, -1],
        bucketCount: 2,
        expected: [
            { minimum: 0, maximum: 1 },
            { minimum: -1, maximum: 0 },
        ],
    },
    {
        name: "gives one bucket per frame for audio shorter than the detail asked for",
        samples: [0.5, -0.25],
        bucketCount: 8,
        expected: [
            { minimum: 0.5, maximum: 0.5 },
            { minimum: -0.25, maximum: -0.25 },
        ],
    },
    {
        name: "reads nothing from a waveform with no frames",
        samples: [],
        bucketCount: 4,
        expected: [],
    },
];

describe("peaksFrom", () => {
    it.each(PEAKS_CASES)("$name", ({ samples, bucketCount, expected }: PeaksCase) => {
        expect(peaksFrom(Float32Array.from(samples), bucketCount)).toEqual(expected);
    });
});

describe("normalized", () => {
    it("scales the peaks so the loudest of them reaches full height", () => {
        expect(
            normalized([
                { minimum: -0.25, maximum: 0.5 },
                { minimum: -0.5, maximum: 0.25 },
            ]),
        ).toEqual([
            { minimum: -0.5, maximum: 1 },
            { minimum: -1, maximum: 0.5 },
        ]);
    });

    it("leaves silence as it stands, having no height to reach", () => {
        expect(normalized([{ minimum: 0, maximum: 0 }])).toEqual([{ minimum: 0, maximum: 0 }]);
    });
});

describe("useAudioPeaks", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("reads back the server's own words about audio it would not serve", async () => {
        vi.stubGlobal(
            "AudioContext",
            class {
                decodeAudioData(): Promise<never> {
                    throw new Error("no audio to decode in this case");
                }
            },
        );
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(
                new Response(JSON.stringify({ detail: REFUSAL }), {
                    status: 422,
                    headers: { "Content-Type": "application/json" },
                }),
            ),
        );

        const { result } = renderHook(() => useAudioPeaks("/api/morph/audio?first=a&second=b&weight=0.625", 8));

        await waitFor(() => {
            expect(result.current.refusal).toBe(REFUSAL);
        });
        expect(result.current.peaks).toBeNull();
    });
});
