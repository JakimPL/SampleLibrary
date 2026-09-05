import { afterEach, describe, expect, it, vi } from "vitest";

import { getCloud, getModuleCloud } from "../../src/api/cloud";

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

describe("getModuleCloud", () => {
    it("requests the module cloud endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getModuleCloud();

        expect(fetchMock).toHaveBeenCalledWith("/cloud/modules");
    });
});
