import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../src/api/cloud";
import { SampleGlance } from "../../src/samples/SampleGlance";

const { getCategoryTags } = vi.hoisted(() => ({ getCategoryTags: vi.fn().mockResolvedValue([]) }));

vi.mock("../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../src/api/cloud");
    return { ...actual, getCategoryTags };
});

describe("SampleGlance", () => {
    it("names the sample over its short hash and badge, with its waveform", () => {
        const { container } = render(
            <SampleGlance
                hash={"a".repeat(64)}
                preview={{ display_name: "kick", category: "BASS DRUM", hand_label: null, thumbnail: [] }}
            />,
        );

        expect(screen.getByText("kick")).toBeInTheDocument();
        expect(screen.getByText("aaaaaaaa")).toBeInTheDocument();
        expect(screen.getByText("BASS DRUM")).toBeInTheDocument();
        expect(container.querySelector("canvas")).toBeInTheDocument();
    });

    it("falls back to the unnamed placeholder", () => {
        render(
            <SampleGlance hash="b" preview={{ display_name: "", category: null, hand_label: null, thumbnail: null }} />,
        );

        expect(screen.getByText("[unnamed]")).toBeInTheDocument();
    });
});
