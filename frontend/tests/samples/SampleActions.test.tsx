import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useMorphStore } from "../../src/morph/morphStore";
import { SampleActions } from "../../src/samples/SampleActions";

describe("SampleActions", () => {
    it("names the sample as either end of the pair and says so once it is", () => {
        render(<SampleActions sampleHash="abc" playbackRateHz={null} />);

        fireEvent.click(screen.getByRole("button", { name: "Morph from here" }));
        expect(useMorphStore.getState().first).toBe("abc");
        expect(screen.getByRole("button", { name: "This is A" })).toBeDisabled();

        fireEvent.click(screen.getByRole("button", { name: "Morph to here" }));

        expect(useMorphStore.getState()).toMatchObject({ first: null, second: "abc" });
        expect(screen.getByRole("button", { name: "This is B" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Morph from here" })).toBeEnabled();
    });
});
