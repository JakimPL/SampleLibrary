import { afterEach, describe, expect, it, vi } from "vitest";

import { getMorphStatus, morphAudioUrl } from "../../src/api/morph";

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("morphAudioUrl", () => {
    it("names the point under the API prefix, the weight written as it was snapped", () => {
        expect(morphAudioUrl("a".repeat(64), "b".repeat(64), 0.0625)).toBe(
            `/api/morph/audio?first=${"a".repeat(64)}&second=${"b".repeat(64)}&weight=0.0625`,
        );
    });
});

describe("getMorphStatus", () => {
    it("requests the morph status endpoint", async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValue({ ok: true, json: () => Promise.resolve({ available: false, service: null }) });
        vi.stubGlobal("fetch", fetchMock);

        await getMorphStatus();

        expect(fetchMock).toHaveBeenCalledWith("/api/morph/status");
    });
});
