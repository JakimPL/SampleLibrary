import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../src/api/samples";
import { MorphDistance } from "../../src/morph/MorphDistance";

const { getSampleDistance } = vi.hoisted(() => ({ getSampleDistance: vi.fn() }));

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, getSampleDistance };
});

describe("MorphDistance", () => {
    it("shows a loading state while the distance request is in flight", () => {
        getSampleDistance.mockReturnValue(new Promise(() => undefined));

        render(<MorphDistance first="abc" second="def" />);

        expect(screen.getByText("Computing distance…")).toBeInTheDocument();
    });

    it("shows the resolved distance between the two ends of the pair", async () => {
        getSampleDistance.mockResolvedValue({ sample_hash: "abc", other_hash: "def", distance: 1.23456 });

        render(<MorphDistance first="abc" second="def" />);

        expect(await screen.findByText("distance 1.235")).toBeInTheDocument();
        expect(getSampleDistance).toHaveBeenCalledWith("abc", "def");
    });

    it("shows an error notice when the distance request fails", async () => {
        getSampleDistance.mockRejectedValue(new Error("no vector yet"));

        render(<MorphDistance first="abc" second="def" />);

        expect(await screen.findByText("no vector yet")).toBeInTheDocument();
    });
});
