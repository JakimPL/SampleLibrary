import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../../src/api/modules";
import type * as SamplesApi from "../../../src/api/samples";
import { CloudHoverTooltip } from "../../../src/workspace/panels/CloudHoverTooltip";

const { getSample, getSampleWaveform, getModule } = vi.hoisted(() => ({
    getSample: vi.fn(),
    getSampleWaveform: vi.fn(),
    getModule: vi.fn(),
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleWaveform };
});

vi.mock("../../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../../src/api/modules");
    return { ...actual, getModule };
});

const SAMPLE_HASH = "a".repeat(64);
const MODULE_HASH = "b".repeat(64);

describe("CloudHoverTooltip", () => {
    it("shows nothing while the sample preview is still loading", () => {
        getSample.mockReturnValue(new Promise(() => undefined));
        getSampleWaveform.mockReturnValue(new Promise(() => undefined));

        const { container } = render(
            <CloudHoverTooltip entity={{ kind: "sample", hash: SAMPLE_HASH }} x={10} y={20} />,
        );

        expect(container).toBeEmptyDOMElement();
    });

    it("shows the sample's display name and short hash once loaded", async () => {
        getSample.mockResolvedValue({
            hash: SAMPLE_HASH,
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [],
            size_bytes: 8192,
            display_name: "kick",
            dominant_rate_hz: 8363,
            duration_seconds: 0.09,
        });
        getSampleWaveform.mockResolvedValue([{ minimum: -0.5, maximum: 0.5 }]);

        render(<CloudHoverTooltip entity={{ kind: "sample", hash: SAMPLE_HASH }} x={10} y={20} />);

        await waitFor(() => {
            expect(screen.getByText("kick")).toBeInTheDocument();
        });
        expect(screen.getByText(SAMPLE_HASH.slice(0, 8))).toBeInTheDocument();
    });

    it("falls back to the unnamed-sample placeholder for an empty display name", async () => {
        getSample.mockResolvedValue({
            hash: SAMPLE_HASH,
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [],
            size_bytes: 8192,
            display_name: "",
            dominant_rate_hz: null,
            duration_seconds: 0.09,
        });
        getSampleWaveform.mockResolvedValue([]);

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
