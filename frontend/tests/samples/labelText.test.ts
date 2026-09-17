import { describe, expect, it } from "vitest";

import { assertsTag, formatPath, topLevelOf, withTag } from "../../src/samples/labelText";

/** One gesture on a label: what it already says, the tag clicked, and what the two rules answer. */
interface TagCase {
    readonly name: string;
    readonly label: string | null;
    readonly tag: string;
    /** Whether the label already asserts the tag, which is what disables the button. */
    readonly taken: boolean;
    readonly written: string;
}

const TAG_CASES: readonly TagCase[] = [
    {
        name: "a label starts from the tag",
        label: null,
        tag: "BASS: ACOUSTIC",
        taken: false,
        written: "BASS: ACOUSTIC",
    },
    { name: "blank text names no tag", label: "  ", tag: "BASS DRUM", taken: false, written: "BASS DRUM" },
    { name: "separators alone name no tag", label: ", :", tag: "SNARE", taken: false, written: "SNARE" },
    { name: "an unrelated tag is appended", label: "SNARE", tag: "LO-FI", taken: false, written: "SNARE, LO-FI" },
    {
        name: "a tag under another top level is appended",
        label: "SNARE",
        tag: "BASS: ACOUSTIC",
        taken: false,
        written: "SNARE, BASS: ACOUSTIC",
    },
    {
        name: "a specification takes the place of the top level it refines",
        label: "BASS",
        tag: "BASS: ACOUSTIC",
        taken: false,
        written: "BASS: ACOUSTIC",
    },
    {
        name: "a top level a specification already asserts is taken",
        label: "BASS: ACOUSTIC",
        tag: "BASS",
        taken: true,
        written: "BASS: ACOUSTIC",
    },
    {
        name: "two specifications under one top level stand side by side",
        label: "BASS: ACOUSTIC",
        tag: "BASS: ELECTRIC",
        taken: false,
        written: "BASS: ACOUSTIC, BASS: ELECTRIC",
    },
    {
        name: "the tag written as it stands is taken",
        label: "BASS: ACOUSTIC",
        tag: "BASS: ACOUSTIC",
        taken: true,
        written: "BASS: ACOUSTIC",
    },
    {
        name: "a refinement keeps the order the tags were written in",
        label: "SNARE, BASS, LO-FI",
        tag: "BASS: ACOUSTIC",
        taken: false,
        written: "SNARE, BASS: ACOUSTIC, LO-FI",
    },
    {
        name: "a tag deeper by two levels still refines",
        label: "BASS",
        tag: "BASS: ACOUSTIC: VINYL",
        taken: false,
        written: "BASS: ACOUSTIC: VINYL",
    },
    {
        name: "a chain of refined tags collapses into the earliest of them",
        label: "BASS, BASS: ACOUSTIC",
        tag: "BASS: ACOUSTIC: VINYL",
        taken: false,
        written: "BASS: ACOUSTIC: VINYL",
    },
    {
        name: "a chain written out of order keeps the first position",
        label: "BASS: ACOUSTIC, SNARE, BASS",
        tag: "BASS: ACOUSTIC: VINYL",
        taken: false,
        written: "BASS: ACOUSTIC: VINYL, SNARE",
    },
    {
        name: "a tag written twice gives way at both places",
        label: "bass, SNARE, BASS",
        tag: "BASS: ACOUSTIC",
        taken: false,
        written: "BASS: ACOUSTIC, SNARE",
    },
    {
        name: "a level is matched whole, not by its opening characters",
        label: "BASSOON",
        tag: "BASS: ACOUSTIC",
        taken: false,
        written: "BASSOON, BASS: ACOUSTIC",
    },
    {
        name: "a space belongs to the level it is written in",
        label: "BASS: ACOUSTIC",
        tag: "BASS DRUM",
        taken: false,
        written: "BASS: ACOUSTIC, BASS DRUM",
    },
    {
        name: "casing and spacing are read through",
        label: "snare, hi-hat :closed",
        tag: "HI-HAT: CLOSED",
        taken: true,
        written: "snare, hi-hat :closed",
    },
    {
        name: "a refinement matches across casing",
        label: "hi-hat",
        tag: "HI-HAT: CLOSED",
        taken: false,
        written: "HI-HAT: CLOSED",
    },
    {
        name: "a rewrite keeps each tag's casing and settles the spacing between them",
        label: "snare ,  lo-fi",
        tag: "BASS",
        taken: false,
        written: "snare, lo-fi, BASS",
    },
    {
        name: "an empty level is read as absent",
        label: "BASS:",
        tag: "BASS: ACOUSTIC",
        taken: false,
        written: "BASS: ACOUSTIC",
    },
    {
        name: "a tag is found wherever it was written",
        label: "BASS: ACOUSTIC, LO-FI",
        tag: "LO-FI",
        taken: true,
        written: "BASS: ACOUSTIC, LO-FI",
    },
];

describe("formatPath", () => {
    it("writes a path the way a person does, one space after each colon", () => {
        expect(formatPath(["HI-HAT", "CLOSED"])).toBe("HI-HAT: CLOSED");
    });
});

describe("topLevelOf", () => {
    it("names the top level of a label's first tag, as the server keeps it", () => {
        expect(topLevelOf("HI-HAT: CLOSED")).toBe("HI-HAT");
        expect(topLevelOf("snare :rim, lo-fi")).toBe("SNARE");
        expect(topLevelOf("BASS DRUM")).toBe("BASS DRUM");
        expect(topLevelOf(" , SNARE")).toBe("SNARE");
    });

    it("names nothing for a label with nothing written", () => {
        expect(topLevelOf("")).toBe("");
        expect(topLevelOf(":")).toBe("");
    });
});

describe("a tag clicked into a label", () => {
    it.each(TAG_CASES)("$name", ({ label, tag, taken, written }) => {
        expect(assertsTag(label, tag)).toBe(taken);
        expect(withTag(label, tag)).toBe(written);
    });
});
