import { afterEach, describe, expect, it, vi } from "vitest";

import { getCloud } from "../../src/api/cloud";

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("getCloud", () => {
    it("requests the cloud endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getCloud();

        expect(fetchMock).toHaveBeenCalledWith("/cloud");
    });
});
