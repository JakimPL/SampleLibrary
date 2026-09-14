import { afterEach, describe, expect, it, vi } from "vitest";

import { changeSampleAnnotation, getLabelTags, getLabelVocabulary } from "../../src/api/curation";

const SAMPLE_HASH = "a".repeat(64);

function stubFetch(payload: unknown): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("changeSampleAnnotation", () => {
    it("sends the decisions a gesture changes and the scope as a PATCH", async () => {
        const fetchMock = stubFetch({ samples: [], skipped: [] });

        await changeSampleAnnotation(SAMPLE_HASH, "sample", { rating: 4 });

        expect(fetchMock).toHaveBeenCalledWith(`/api/curation/annotations/${SAMPLE_HASH}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rating: 4, scope: "sample" }),
        });
    });

    it("sends a cleared decision as null", async () => {
        const fetchMock = stubFetch({ samples: [], skipped: [] });

        await changeSampleAnnotation(SAMPLE_HASH, "equivalence_class", { label: null });

        expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
            body: JSON.stringify({ label: null, scope: "equivalence_class" }),
        });
    });

    it("reports what every reached sample says afterward", async () => {
        stubFetch({
            samples: [
                { sample_hash: SAMPLE_HASH, annotation: { label: "SNARE", rating: null, favorite: false } },
                { sample_hash: "b".repeat(64), annotation: null },
            ],
            skipped: [],
        });

        const written = await changeSampleAnnotation(SAMPLE_HASH, "equivalence_class", { label: "snare" });

        expect(written.samples).toHaveLength(2);
    });
});

describe("getLabelVocabulary", () => {
    it("requests the vocabulary endpoint", async () => {
        const fetchMock = stubFetch([]);

        await getLabelVocabulary();

        expect(fetchMock).toHaveBeenCalledWith("/api/curation/annotations/vocabulary");
    });
});

describe("getLabelTags", () => {
    it("requests the tags endpoint", async () => {
        const fetchMock = stubFetch([]);

        await getLabelTags();

        expect(fetchMock).toHaveBeenCalledWith("/api/curation/annotations/tags");
    });
});
