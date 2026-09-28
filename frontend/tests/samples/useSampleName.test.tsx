import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SampleName } from "../../src/samples/SampleName";
import { spokenNameOf } from "../../src/samples/useSampleName";
import { shortHash } from "../../src/shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../../src/shared/labels";

const HASH = "a".repeat(64);

/** One answer of the catalog about a sample's name, and what is said and shown for it. */
interface NameCase {
    readonly name: string;
    readonly given: string | null;
    readonly shown: string;
}

const NAME_CASES: readonly NameCase[] = [
    { name: "a named sample by its name", given: "kick_808", shown: "kick_808" },
    { name: "a sample named with nothing by the unnamed label", given: "", shown: UNNAMED_SAMPLE_LABEL },
    { name: "a sample the catalog has yet to name by its short hash", given: null, shown: shortHash(HASH) },
];

describe("spokenNameOf", () => {
    it.each(NAME_CASES)("speaks of $name", ({ given, shown }: NameCase) => {
        expect(spokenNameOf(HASH, given)).toBe(shown);
    });
});

describe("SampleName", () => {
    it.each(NAME_CASES)("shows $name", ({ given, shown }: NameCase) => {
        render(<SampleName hash={HASH} name={given} />);

        expect(screen.getByText(shown)).toBeInTheDocument();
    });

    it("sets the short hash in mono, as every hash is", () => {
        render(<SampleName hash={HASH} name={null} />);

        expect(screen.getByText(shortHash(HASH))).toHaveClass("mono");
    });
});
