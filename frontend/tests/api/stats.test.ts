import { afterEach, describe, expect, it, vi } from "vitest";

import { getStats } from "../../src/api/stats";

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("getStats", () => {
    it("requests the stats endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ module_count: 0 }) });
        vi.stubGlobal("fetch", fetchMock);

        await getStats();

        expect(fetchMock).toHaveBeenCalledWith("/api/stats");
    });
});
