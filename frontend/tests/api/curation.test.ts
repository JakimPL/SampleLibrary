import { afterEach, describe, expect, it, vi } from "vitest";

import { clearSampleLabel, getLabelVocabulary, setSampleLabel } from "../../src/api/curation";

const SAMPLE_HASH = "a".repeat(64);

function stubFetch(payload: unknown): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("setSampleLabel", () => {
    it("sends the chosen wording and scope as a PUT", async () => {
        const fetchMock = stubFetch({ label: "warm pad", sample_hashes: [SAMPLE_HASH] });

        await setSampleLabel(SAMPLE_HASH, "warm pad", "sample");

        expect(fetchMock).toHaveBeenCalledWith(`/curation/labels/${SAMPLE_HASH}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label: "warm pad", scope: "sample" }),
        });
    });

    it("carries a group scope through to the server", async () => {
        const fetchMock = stubFetch({ label: "snare", sample_hashes: [SAMPLE_HASH] });

        await setSampleLabel(SAMPLE_HASH, "snare", "equivalence_class");

        expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
            body: JSON.stringify({ label: "snare", scope: "equivalence_class" }),
        });
    });

    it("reports back which samples the labelling reached", async () => {
        stubFetch({ label: "snare", sample_hashes: [SAMPLE_HASH, "b".repeat(64)] });

        const written = await setSampleLabel(SAMPLE_HASH, "snare", "equivalence_class");

        expect(written.sample_hashes).toHaveLength(2);
    });
});

describe("clearSampleLabel", () => {
    it("sends a DELETE naming the scope, with no body", async () => {
        const fetchMock = stubFetch({ label: null, sample_hashes: [SAMPLE_HASH] });

        await clearSampleLabel(SAMPLE_HASH, "sample");

        expect(fetchMock).toHaveBeenCalledWith(`/curation/labels/${SAMPLE_HASH}?scope=sample`, { method: "DELETE" });
    });
});

describe("getLabelVocabulary", () => {
    it("requests the vocabulary endpoint", async () => {
        const fetchMock = stubFetch([]);

        await getLabelVocabulary();

        expect(fetchMock).toHaveBeenCalledWith("/curation/labels/vocabulary");
    });
});
