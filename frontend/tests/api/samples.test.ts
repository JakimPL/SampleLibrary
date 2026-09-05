import { afterEach, describe, expect, it, vi } from "vitest";

import { getSample, getSampleRelations, getSampleWaveform, listSamples, sampleAudioUrl } from "../../src/api/samples";

function stubFetchReturning(payload: unknown): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("listSamples", () => {
    it("builds a query string from limit and offset", async () => {
        const fetchMock = stubFetchReturning({ items: [], total: 0, limit: 50, offset: 0 });

        await listSamples({ limit: 50, offset: 0 });

        expect(fetchMock).toHaveBeenCalledWith("/samples?limit=50&offset=0");
    });
});

describe("getSample", () => {
    it("requests the sample by hash", async () => {
        const fetchMock = stubFetchReturning({ hash: "abc" });

        await getSample("abc");

        expect(fetchMock).toHaveBeenCalledWith("/samples/abc");
    });
});

describe("getSampleRelations", () => {
    it("requests the sample's relations", async () => {
        const fetchMock = stubFetchReturning([]);

        await getSampleRelations("abc");

        expect(fetchMock).toHaveBeenCalledWith("/samples/abc/relations");
    });
});

describe("getSampleWaveform", () => {
    it("requests the sample's waveform peaks", async () => {
        const fetchMock = stubFetchReturning([]);

        await getSampleWaveform("abc");

        expect(fetchMock).toHaveBeenCalledWith("/samples/abc/waveform");
    });
});

describe("sampleAudioUrl", () => {
    it("builds the audio URL without fetching anything", () => {
        expect(sampleAudioUrl("abc")).toBe("/samples/abc/audio");
    });
});
