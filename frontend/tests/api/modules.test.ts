import { afterEach, describe, expect, it, vi } from "vitest";

import { getModule, listModules } from "../../src/api/modules";

function stubFetchReturning(payload: unknown): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

describe("listModules", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("builds a query string from limit, offset, and no tracker filter", async () => {
        const fetchMock = stubFetchReturning({ items: [], total: 0, limit: 50, offset: 0 });

        await listModules({ limit: 50, offset: 0, tracker: null });

        expect(fetchMock).toHaveBeenCalledWith("/modules?limit=50&offset=0");
    });

    it("includes the tracker filter when one is given", async () => {
        const fetchMock = stubFetchReturning({ items: [], total: 0, limit: 50, offset: 0 });

        await listModules({ limit: 50, offset: 0, tracker: "xm" });

        expect(fetchMock).toHaveBeenCalledWith("/modules?limit=50&offset=0&tracker=xm");
    });
});

describe("getModule", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("requests the module by hash", async () => {
        const fetchMock = stubFetchReturning({ hash: "abc" });

        await getModule("abc");

        expect(fetchMock).toHaveBeenCalledWith("/modules/abc");
    });
});
