import { afterEach, describe, expect, it, vi } from "vitest";

import { getSample, getSampleRelations } from "../../src/api/samples";

function stubFetchReturning(payload: unknown): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

afterEach(() => {
    vi.unstubAllGlobals();
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
