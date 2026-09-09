import { afterEach, describe, expect, it, vi } from "vitest";

import {
    getSample,
    getSampleDistance,
    getSampleRelations,
    getSimilarSamples,
    listSamples,
    sampleAudioUrl,
    WHOLE_CATALOG,
} from "../../src/api/samples";

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

        await listSamples({ limit: 50, offset: 0, groupByEquivalence: false, selection: WHOLE_CATALOG });

        expect(fetchMock).toHaveBeenCalledWith(
            "/api/samples?limit=50&offset=0&group_by_equivalence=false&favorites_only=false&sort=occurrences",
        );
    });

    it("carries a narrowing a person has asked for", async () => {
        const fetchMock = stubFetchReturning({ items: [], total: 0, limit: 50, offset: 0 });

        await listSamples({
            limit: 50,
            offset: 0,
            groupByEquivalence: false,
            selection: { favoritesOnly: true, sort: "rating" },
        });

        expect(fetchMock).toHaveBeenCalledWith(
            "/api/samples?limit=50&offset=0&group_by_equivalence=false&favorites_only=true&sort=rating",
        );
    });

    it("passes the equivalence grouping flag through to the query string", async () => {
        const fetchMock = stubFetchReturning({ items: [], total: 0, limit: 50, offset: 0 });

        await listSamples({ limit: 50, offset: 0, groupByEquivalence: true, selection: WHOLE_CATALOG });

        expect(fetchMock).toHaveBeenCalledWith(
            "/api/samples?limit=50&offset=0&group_by_equivalence=true&favorites_only=false&sort=occurrences",
        );
    });
});

describe("getSample", () => {
    it("requests the sample by hash", async () => {
        const fetchMock = stubFetchReturning({ hash: "abc" });

        await getSample("abc");

        expect(fetchMock).toHaveBeenCalledWith("/api/samples/abc");
    });
});

describe("getSampleRelations", () => {
    it("requests the sample's relations", async () => {
        const fetchMock = stubFetchReturning([]);

        await getSampleRelations("abc");

        expect(fetchMock).toHaveBeenCalledWith("/api/samples/abc/relations");
    });
});

describe("getSampleDistance", () => {
    it("requests the distance between two samples", async () => {
        const fetchMock = stubFetchReturning({ sample_hash: "abc", other_hash: "def", distance: 1.5 });

        await getSampleDistance("abc", "def");

        expect(fetchMock).toHaveBeenCalledWith("/api/samples/abc/distance/def");
    });
});

describe("getSimilarSamples", () => {
    it("requests the sample's spectral neighbors", async () => {
        const fetchMock = stubFetchReturning([]);

        await getSimilarSamples("abc");

        expect(fetchMock).toHaveBeenCalledWith("/api/samples/abc/similar");
    });
});

describe("sampleAudioUrl", () => {
    it("builds the audio URL without fetching anything", () => {
        expect(sampleAudioUrl("abc")).toBe("/api/samples/abc/audio");
    });
});
