import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../src/api/samples";
import { SampleDetailPage } from "../../src/samples/SampleDetailPage";

const { getSample, getSampleRelations } = vi.hoisted(() => ({ getSample: vi.fn(), getSampleRelations: vi.fn() }));

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, getSample, getSampleRelations };
});

function renderPage(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/samples/sample-1"]}>
            <Routes>
                <Route path="/samples/:sampleHash" element={<SampleDetailPage />} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("SampleDetailPage", () => {
    it("renders occurrences and links a relation to the other sample in the pair", async () => {
        getSample.mockResolvedValue({
            hash: "sample-1",
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [
                {
                    sample_hash: "sample-1",
                    occurrence: { module_hash: "module-1", instrument_index: 0, sample_slot: 0 },
                    name: "lead",
                    rate: 8363,
                    volume: 64,
                    tracker: "xm",
                    tuning: { relative_note: 0, finetune: 0 },
                },
            ],
        });
        getSampleRelations.mockResolvedValue([
            {
                id: 1,
                subject_hash: "sample-1",
                reference_hash: "sample-2",
                relation_type: "bit_depth_variant",
                method: "bit_depth_variant/mse_v1",
                confidence: 0.9,
                evidence: {},
                detected_at: "2026-01-01T00:00:00Z",
            },
        ]);

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("heading", { name: "Sample sample-1" })).toBeInTheDocument();
        });
        expect(screen.getByRole("link", { name: "module-1" })).toHaveAttribute("href", "/modules/module-1");
        expect(screen.getByRole("link", { name: "sample-2" })).toHaveAttribute("href", "/samples/sample-2");
    });

    it("shows an error notice when the sample cannot be found", async () => {
        getSample.mockRejectedValue(new Error("no sample catalogued with hash 'sample-1'"));
        getSampleRelations.mockRejectedValue(new Error("no sample catalogued with hash 'sample-1'"));

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("no sample catalogued with hash 'sample-1'");
        });
    });
});
