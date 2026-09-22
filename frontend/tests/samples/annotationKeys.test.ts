import { describe, expect, it } from "vitest";

import type { AnnotationChanges, AnnotationDecisions } from "../../src/api/curation";
import { annotationKeyChange } from "../../src/samples/annotationKeys";

interface KeyCase {
    readonly key: string;
    readonly decisions: AnnotationDecisions;
    readonly expected: AnnotationChanges | null;
}

const UNRATED: AnnotationDecisions = { label: null, rating: null, favorite: false };

describe("annotationKeyChange", () => {
    it.each<KeyCase>([
        { key: "f", decisions: UNRATED, expected: { favorite: true } },
        { key: "F", decisions: { ...UNRATED, favorite: true }, expected: { favorite: false } },
        { key: "3", decisions: UNRATED, expected: { rating: 3 } },
        { key: "3", decisions: { ...UNRATED, rating: 3 }, expected: { rating: null } },
        { key: "6", decisions: UNRATED, expected: null },
        { key: "Enter", decisions: UNRATED, expected: null },
    ])("reads $key as $expected", ({ key, decisions, expected }) => {
        expect(annotationKeyChange(key, decisions)).toEqual(expected);
    });
});
