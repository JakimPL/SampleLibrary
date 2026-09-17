import { afterEach, describe, expect, it, vi } from "vitest";

import { getCategoryTags, getCloud, getCloudCategories, getCloudLabels, getModuleCloud } from "../../src/api/cloud";

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("getCloud", () => {
    it("requests the cloud endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getCloud();

        expect(fetchMock).toHaveBeenCalledWith("/api/cloud");
    });
});

describe("getModuleCloud", () => {
    it("requests the module cloud endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getModuleCloud();

        expect(fetchMock).toHaveBeenCalledWith("/api/cloud/modules");
    });
});

describe("getCloudLabels", () => {
    it("requests the cloud's labels endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getCloudLabels();

        expect(fetchMock).toHaveBeenCalledWith("/api/cloud/labels");
    });
});

describe("getCloudCategories", () => {
    it("requests the cloud's categories endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getCloudCategories();

        expect(fetchMock).toHaveBeenCalledWith("/api/cloud/suggestions");
    });
});

describe("getCategoryTags", () => {
    it("requests the category tags endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getCategoryTags();

        expect(fetchMock).toHaveBeenCalledWith("/api/cloud/suggestion-tags");
    });
});
