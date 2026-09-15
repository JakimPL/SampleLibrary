import type { IncomingMessage, ServerResponse } from "node:http";

import type { ViteDevServer } from "vite";
import { afterEach, describe, expect, it, vi } from "vitest";

import { densifyPoints, parseDensifyTarget } from "../../dev/densifyCloud";
import { densifyCloudPlugin } from "../../dev/densifyCloudPlugin";

interface SamplePoint {
    readonly sample_hash: string;
    readonly x: number;
    readonly y: number;
    readonly category: string;
    readonly playback_rate_hz: number | null;
}

interface ModulePoint {
    readonly module_hash: string;
    readonly x: number;
    readonly y: number;
}

type Handle = (request: IncomingMessage, response: ServerResponse, next: (error?: unknown) => void) => void;

const KICK_HASH = "a".repeat(64);
const SUBSTRATE_HASH = "b".repeat(64);
const PAD_HASH = "c".repeat(64);

const SAMPLES: readonly SamplePoint[] = [
    { sample_hash: KICK_HASH, x: 0, y: 0, category: "kick", playback_rate_hz: 44100 },
    { sample_hash: SUBSTRATE_HASH, x: 10, y: 5, category: "uncategorized", playback_rate_hz: null },
    { sample_hash: PAD_HASH, x: -3, y: 7, category: "pad", playback_rate_hz: 22050 },
];

const unitWeight = (): number => 1;

function decimalsOf(value: number): number {
    const text = value.toString();
    const separator = text.indexOf(".");
    return separator === -1 ? 0 : text.length - separator - 1;
}

describe("densifyPoints", () => {
    it("answers with the target count, the originals first and unchanged", () => {
        const grown = densifyPoints(SAMPLES, { targetCount: 1000, seed: 1, weightOf: unitWeight });

        expect(grown).toHaveLength(1000);
        expect(grown.slice(0, SAMPLES.length)).toEqual(SAMPLES);
    });

    it("gives every clone a real point's hash, category and rate", () => {
        const byHash = new Map(SAMPLES.map((sample) => [sample.sample_hash, sample]));
        const grown = densifyPoints(SAMPLES, { targetCount: 500, seed: 2, weightOf: unitWeight });

        for (const clone of grown.slice(SAMPLES.length)) {
            const parent = byHash.get(clone.sample_hash);
            expect(parent).toBeDefined();
            expect(clone.category).toBe(parent?.category);
            expect(clone.playback_rate_hz).toBe(parent?.playback_rate_hz);
        }
    });

    it("repeats the same cloud for the same seed and another for another seed", () => {
        const first = densifyPoints(SAMPLES, { targetCount: 300, seed: 7, weightOf: unitWeight });
        const again = densifyPoints(SAMPLES, { targetCount: 300, seed: 7, weightOf: unitWeight });
        const other = densifyPoints(SAMPLES, { targetCount: 300, seed: 8, weightOf: unitWeight });

        expect(again).toEqual(first);
        expect(other).not.toEqual(first);
    });

    it.each([
        { name: "a target equal to the input's length", points: SAMPLES, targetCount: 3 },
        { name: "a target below the input's length", points: SAMPLES, targetCount: 1 },
        { name: "no points at all", points: [] as readonly SamplePoint[], targetCount: 100 },
    ])("returns the input unchanged for $name", ({ points, targetCount }) => {
        expect(densifyPoints(points, { targetCount, seed: 1, weightOf: unitWeight })).toBe(points);
    });

    it("rounds every coordinate to four decimals", () => {
        const grown = densifyPoints(SAMPLES, { targetCount: 400, seed: 3, weightOf: unitWeight });

        for (const point of grown) {
            expect(decimalsOf(point.x)).toBeLessThanOrEqual(4);
            expect(decimalsOf(point.y)).toBeLessThanOrEqual(4);
        }
    });

    it("spreads clones around their parent, within one span of the cloud's box", () => {
        const grown = densifyPoints(SAMPLES, { targetCount: 3003, seed: 4, weightOf: unitWeight });
        const kickClones = grown.slice(SAMPLES.length).filter((point) => point.sample_hash === KICK_HASH);
        const meanX = kickClones.reduce((sum, point) => sum + point.x, 0) / kickClones.length;
        const meanY = kickClones.reduce((sum, point) => sum + point.y, 0) / kickClones.length;
        const varianceX = kickClones.reduce((sum, point) => sum + (point.x - meanX) ** 2, 0) / kickClones.length;

        expect(kickClones.length).toBeGreaterThan(300);
        expect(Math.abs(meanX)).toBeLessThan(0.5);
        expect(Math.abs(meanY)).toBeLessThan(0.5);
        expect(varianceX).toBeGreaterThan(0);
        for (const point of grown) {
            expect(point.x).toBeGreaterThanOrEqual(-3 - 13);
            expect(point.x).toBeLessThanOrEqual(10 + 13);
            expect(point.y).toBeGreaterThanOrEqual(0 - 13);
            expect(point.y).toBeLessThanOrEqual(7 + 13);
        }
    });

    it("grows a heavier point into the largest cluster", () => {
        const grown = densifyPoints(SAMPLES, {
            targetCount: 3003,
            seed: 5,
            weightOf: (point) => (point.sample_hash === SUBSTRATE_HASH ? 8 : 1),
        });
        const countOf = (hash: string): number => grown.filter((point) => point.sample_hash === hash).length;

        expect(countOf(SUBSTRATE_HASH)).toBeGreaterThan(countOf(KICK_HASH));
        expect(countOf(SUBSTRATE_HASH)).toBeGreaterThan(countOf(PAD_HASH));
    });

    it("grows module points the same way", () => {
        const modules: readonly ModulePoint[] = [
            { module_hash: "d".repeat(64), x: 1, y: 1 },
            { module_hash: "e".repeat(64), x: -1, y: -1 },
        ];
        const hashes = new Set(modules.map((module) => module.module_hash));
        const grown = densifyPoints(modules, { targetCount: 50, seed: 6, weightOf: unitWeight });

        expect(grown).toHaveLength(50);
        expect(grown.every((point) => hashes.has(point.module_hash))).toBe(true);
    });
});

describe("parseDensifyTarget", () => {
    it.each([
        { text: undefined, expected: null },
        { text: "", expected: null },
        { text: "  ", expected: null },
        { text: "abc", expected: null },
        { text: "0", expected: null },
        { text: "-5", expected: null },
        { text: "12.5", expected: null },
        { text: "100000", expected: 100000 },
    ])("reads $text as $expected", ({ text, expected }) => {
        expect(parseDensifyTarget(text)).toBe(expected);
    });
});

describe("densifyCloudPlugin", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    function configure(
        sampleTargetText: string | undefined,
        moduleTargetText: string | undefined,
    ): { readonly use: ReturnType<typeof vi.fn>; readonly info: ReturnType<typeof vi.fn> } {
        const plugin = densifyCloudPlugin({ backendUrl: "http://backend.test", sampleTargetText, moduleTargetText });
        const hook = plugin.configureServer;
        if (typeof hook !== "function") {
            throw new Error("the plugin registers configureServer as a function");
        }
        const use = vi.fn();
        const info = vi.fn();
        void hook({ config: { logger: { info } }, middlewares: { use } } as unknown as ViteDevServer);
        return { use, info };
    }

    function registeredHandle(use: ReturnType<typeof vi.fn>): Handle {
        return use.mock.calls[0]?.[0] as Handle;
    }

    function fakeResponse(): {
        statusCode: number;
        setHeader: ReturnType<typeof vi.fn>;
        end: ReturnType<typeof vi.fn>;
    } {
        return { statusCode: 200, setHeader: vi.fn(), end: vi.fn() };
    }

    it("registers nothing when no target is set", () => {
        const { use, info } = configure(undefined, "");

        expect(use).not.toHaveBeenCalled();
        expect(info).not.toHaveBeenCalled();
    });

    it("answers the sample cloud with the grown points", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(SAMPLES) });
        vi.stubGlobal("fetch", fetchMock);
        const { use, info } = configure("200", undefined);
        const response = fakeResponse();
        const next = vi.fn();

        registeredHandle(use)(
            { method: "GET", url: "/api/cloud" } as IncomingMessage,
            response as unknown as ServerResponse,
            next,
        );
        await vi.waitFor(() => {
            expect(response.end).toHaveBeenCalledTimes(1);
        });

        expect(info).toHaveBeenCalledWith(expect.stringContaining("200"));
        expect(fetchMock).toHaveBeenCalledWith(new URL("/api/cloud", "http://backend.test"));
        expect(response.setHeader).toHaveBeenCalledWith("Content-Type", "application/json");
        const body = JSON.parse(response.end.mock.calls[0]?.[0] as string) as readonly SamplePoint[];
        expect(body).toHaveLength(200);
        expect(body.slice(0, SAMPLES.length)).toEqual(SAMPLES);
        expect(next).not.toHaveBeenCalled();
    });

    it("lays the catalog's own samples out when the embedding has yet to run", async () => {
        const listing = {
            items: [
                {
                    hash: KICK_HASH,
                    display_name: "kick 01",
                    category: "kick",
                    hand_label: null,
                    suggested_label: "BASS DRUM",
                    playback_rate_hz: 44100,
                },
                {
                    hash: PAD_HASH,
                    display_name: "warm_pad",
                    category: "pad",
                    hand_label: null,
                    suggested_label: null,
                    playback_rate_hz: null,
                },
            ],
        };
        const fetchMock = vi.fn().mockImplementation((url: URL) => {
            const body = url.pathname === "/api/cloud" ? [] : listing;
            return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
        });
        vi.stubGlobal("fetch", fetchMock);
        const { use } = configure("100", undefined);
        const response = fakeResponse();
        const next = vi.fn();

        registeredHandle(use)(
            { method: "GET", url: "/api/cloud" } as IncomingMessage,
            response as unknown as ServerResponse,
            next,
        );
        await vi.waitFor(() => {
            expect(response.end).toHaveBeenCalledTimes(1);
        });

        expect(fetchMock.mock.calls.map((call) => (call[0] as URL).pathname)).toEqual(["/api/cloud", "/api/samples"]);
        const body = JSON.parse(response.end.mock.calls[0]?.[0] as string) as readonly SamplePoint[];
        expect(body).toHaveLength(100);
        expect(new Set(body.map((point) => point.sample_hash))).toEqual(new Set([KICK_HASH, PAD_HASH]));
        expect(body.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y))).toBe(true);
        expect(next).not.toHaveBeenCalled();
    });

    it("passes every other route on", () => {
        const fetchMock = vi.fn();
        vi.stubGlobal("fetch", fetchMock);
        const { use } = configure("200", undefined);
        const handle = registeredHandle(use);
        const response = fakeResponse();
        const next = vi.fn();

        handle(
            { method: "GET", url: "/api/cloud/labels" } as IncomingMessage,
            response as unknown as ServerResponse,
            next,
        );
        handle(
            { method: "GET", url: "/api/cloud/modules" } as IncomingMessage,
            response as unknown as ServerResponse,
            next,
        );
        handle({ method: "POST", url: "/api/cloud" } as IncomingMessage, response as unknown as ServerResponse, next);

        expect(next).toHaveBeenCalledTimes(3);
        expect(fetchMock).not.toHaveBeenCalled();
        expect(response.end).not.toHaveBeenCalled();
    });
});
