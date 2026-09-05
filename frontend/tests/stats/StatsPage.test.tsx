import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as StatsApi from "../../src/api/stats";
import { StatsPage } from "../../src/stats/StatsPage";

const { getStats } = vi.hoisted(() => ({ getStats: vi.fn() }));

vi.mock("../../src/api/stats", async () => {
    const actual = await vi.importActual<typeof StatsApi>("../../src/api/stats");
    return { ...actual, getStats };
});

describe("StatsPage", () => {
    it("renders the fetched library stats", async () => {
        getStats.mockResolvedValue({
            module_count: 149,
            sample_count: 4905,
            sample_properties_count: 5113,
            modules_by_tracker: [{ tracker: "xm", module_count: 110 }],
            relations_by_type: [{ relation_type: "resampled_variant", relation_count: 12 }],
            total_stored_bytes: 199_989_683,
        });

        render(<StatsPage />);

        await waitFor(() => {
            expect(screen.getByText("149")).toBeInTheDocument();
        });
        expect(screen.getByText("xm: 110")).toBeInTheDocument();
        expect(screen.getByText("resampled_variant: 12")).toBeInTheDocument();
    });

    it("shows an error notice when the stats request fails", async () => {
        getStats.mockRejectedValue(new Error("service unavailable"));

        render(<StatsPage />);

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("service unavailable");
        });
    });
});
