import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../../src/api/modules";
import type * as SamplesApi from "../../../src/api/samples";
import { CloudHoverTooltip } from "../../../src/workspace/panels/CloudHoverTooltip";

const { getSamplePreview, getModule } = vi.hoisted(() => ({
    getSamplePreview: vi.fn(),
    getModule: vi.fn(),
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSamplePreview };
});

vi.mock("../../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../../src/api/modules");
    return { ...actual, getModule };
});

const SAMPLE_HASH = "a".repeat(64);
const MODULE_HASH = "b".repeat(64);

describe("CloudHoverTooltip", () => {
    it("shows nothing while the sample preview is still loading", () => {
        getSamplePreview.mockReturnValue(new Promise(() => undefined));

        const { container } = render(
            <CloudHoverTooltip entity={{ kind: "sample", hash: SAMPLE_HASH }} x={10} y={20} />,
        );

        expect(container).toBeEmptyDOMElement();
    });

    it("shows the sample's display name and short hash once the one preview request lands", async () => {
        getSamplePreview.mockResolvedValue({
            display_name: "kick",
            category: "kick",
            hand_label: null,
            thumbnail: [{ minimum: -0.5, maximum: 0.5 }],
        });

        render(<CloudHoverTooltip entity={{ kind: "sample", hash: SAMPLE_HASH }} x={10} y={20} />);

        await waitFor(() => {
            expect(screen.getByText("kick")).toBeInTheDocument();
        });
        expect(screen.getByText(SAMPLE_HASH.slice(0, 8))).toBeInTheDocument();
        expect(screen.getByText("Kick")).toBeInTheDocument();
        expect(getSamplePreview).toHaveBeenCalledWith(SAMPLE_HASH);
    });

    it("falls back to the unnamed-sample placeholder for an empty display name, with no thumbnail yet", async () => {
        getSamplePreview.mockResolvedValue({
            display_name: "",
            category: "uncategorized",
            hand_label: null,
            thumbnail: null,
        });

        render(<CloudHoverTooltip entity={{ kind: "sample", hash: SAMPLE_HASH }} x={10} y={20} />);

        expect(await screen.findByText("[unnamed]")).toBeInTheDocument();
    });

    it("shows the module's title, short hash, and tracker once loaded", async () => {
        getModule.mockResolvedValue({
            hash: MODULE_HASH,
            id: 1,
            title: "A Song",
            filename: "song.xm",
            tracker: "xm",
            channel_count: 4,
            pattern_count: 2,
            instrument_count: 1,
            sample_count: 0,
            file_size: 4096,
            ingested_at: "2026-01-01T00:00:00Z",
            occurrences: [],
        });

        render(<CloudHoverTooltip entity={{ kind: "module", hash: MODULE_HASH }} x={10} y={20} />);

        await waitFor(() => {
            expect(screen.getByText("A Song")).toBeInTheDocument();
        });
        expect(screen.getByText(MODULE_HASH.slice(0, 8))).toBeInTheDocument();
        expect(screen.getByText("xm")).toBeInTheDocument();
    });

    it("falls back to the untitled-module placeholder for an empty title", async () => {
        getModule.mockResolvedValue({
            hash: MODULE_HASH,
            id: 1,
            title: "",
            filename: "song.xm",
            tracker: "it",
            channel_count: 4,
            pattern_count: 2,
            instrument_count: 1,
            sample_count: 0,
            file_size: 4096,
            ingested_at: "2026-01-01T00:00:00Z",
            occurrences: [],
        });

        render(<CloudHoverTooltip entity={{ kind: "module", hash: MODULE_HASH }} x={10} y={20} />);

        expect(await screen.findByText("[untitled]")).toBeInTheDocument();
    });
});
