import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModuleGlance } from "../../src/modules/ModuleGlance";

describe("ModuleGlance", () => {
    it("names the module over its short hash and tracker", () => {
        render(
            <ModuleGlance
                hash={"b".repeat(64)}
                module={{
                    hash: "b".repeat(64),
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
                }}
            />,
        );

        expect(screen.getByText("A Song")).toBeInTheDocument();
        expect(screen.getByText("bbbbbbbb")).toBeInTheDocument();
        expect(screen.getByText("xm")).toBeInTheDocument();
    });
});
