import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as StatsApi from "../../../src/api/stats";
import { StatsPanel } from "../../../src/workspace/panels/StatsPanel";

const { getStats } = vi.hoisted(() => ({ getStats: vi.fn() }));

vi.mock("../../../src/api/stats", async () => {
    const actual = await vi.importActual<typeof StatsApi>("../../../src/api/stats");
    return { ...actual, getStats };
});

describe("StatsPanel", () => {
    it("shows a loading state before the stats arrive", () => {
        getStats.mockReturnValue(new Promise(() => undefined));

        render(<StatsPanel />);

        expect(screen.getByText("Loading…")).toBeInTheDocument();
    });

    it("renders the fetched stats once loaded", async () => {
        getStats.mockResolvedValue({
            module_count: 2,
            sample_count: 5,
            sample_properties_count: 5,
            total_stored_bytes: 1024,
            modules_by_tracker: [{ tracker: "xm", module_count: 2 }],
            relations_by_type: [{ relation_type: "resampled_variant", relation_count: 1 }],
        });

        render(<StatsPanel />);

        await waitFor(() => {
            expect(screen.getByText("2")).toBeInTheDocument();
        });
        expect(screen.getByText("xm: 2")).toBeInTheDocument();
        expect(screen.getByText("resampled_variant: 1")).toBeInTheDocument();
    });

    it("shows an error notice when the request fails", async () => {
        getStats.mockRejectedValue(new Error("service unavailable"));

        render(<StatsPanel />);

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("service unavailable");
        });
    });
});
