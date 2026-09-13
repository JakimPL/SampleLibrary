import { afterEach, describe, expect, it, vi } from "vitest";

import { getCloud, getCloudLabels, getCloudSuggestions, getModuleCloud, getSuggestionTags } from "../../src/api/cloud";

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

describe("getCloudSuggestions", () => {
    it("requests the cloud's suggestions endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getCloudSuggestions();

        expect(fetchMock).toHaveBeenCalledWith("/api/cloud/suggestions");
    });
});

describe("getSuggestionTags", () => {
    it("requests the suggested tags endpoint", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
        vi.stubGlobal("fetch", fetchMock);

        await getSuggestionTags();

        expect(fetchMock).toHaveBeenCalledWith("/api/cloud/suggestion-tags");
    });
});
