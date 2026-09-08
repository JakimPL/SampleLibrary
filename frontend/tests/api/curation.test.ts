import { afterEach, describe, expect, it, vi } from "vitest";

import { clearSampleAnnotation, getLabelVocabulary, setSampleAnnotation } from "../../src/api/curation";

const SAMPLE_HASH = "a".repeat(64);
const NOTHING = { label: null, rating: null, favorite: false };

function stubFetch(payload: unknown): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("setSampleAnnotation", () => {
    it("sends every decision and the scope as a PUT", async () => {
        const fetchMock = stubFetch({ annotation: null, sample_hashes: [SAMPLE_HASH] });

        await setSampleAnnotation(SAMPLE_HASH, { label: "warm pad", rating: 4, favorite: true }, "sample");

        expect(fetchMock).toHaveBeenCalledWith(`/curation/annotations/${SAMPLE_HASH}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label: "warm pad", rating: 4, favorite: true, scope: "sample" }),
        });
    });

    it("carries a group scope through to the server", async () => {
        const fetchMock = stubFetch({ annotation: null, sample_hashes: [SAMPLE_HASH] });

        await setSampleAnnotation(SAMPLE_HASH, { ...NOTHING, label: "snare" }, "equivalence_class");

        expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
            body: JSON.stringify({ label: "snare", rating: null, favorite: false, scope: "equivalence_class" }),
        });
    });

    it("reports back which samples the gesture reached", async () => {
        stubFetch({
            annotation: { label: "snare", rating: null, favorite: false },
            sample_hashes: [SAMPLE_HASH, "b".repeat(64)],
        });

        const written = await setSampleAnnotation(SAMPLE_HASH, { ...NOTHING, label: "snare" }, "equivalence_class");

        expect(written.sample_hashes).toHaveLength(2);
    });
});

describe("clearSampleAnnotation", () => {
    it("sends a state recording nothing, which is what takes every decision back", async () => {
        const fetchMock = stubFetch({ annotation: null, sample_hashes: [SAMPLE_HASH] });

        await clearSampleAnnotation(SAMPLE_HASH, "sample");

        expect(fetchMock).toHaveBeenCalledWith(`/curation/annotations/${SAMPLE_HASH}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label: null, rating: null, favorite: false, scope: "sample" }),
        });
    });
});

describe("getLabelVocabulary", () => {
    it("requests the vocabulary endpoint", async () => {
        const fetchMock = stubFetch([]);

        await getLabelVocabulary();

        expect(fetchMock).toHaveBeenCalledWith("/curation/annotations/vocabulary");
    });
});
