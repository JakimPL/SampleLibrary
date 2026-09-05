import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../src/api/modules";
import { ModuleDetailPage } from "../../src/modules/ModuleDetailPage";

const { getModule } = vi.hoisted(() => ({ getModule: vi.fn() }));

vi.mock("../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../src/api/modules");
    return { ...actual, getModule };
});

function renderPage(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/modules/abc"]}>
            <Routes>
                <Route path="/modules/:moduleHash" element={<ModuleDetailPage />} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("ModuleDetailPage", () => {
    it("renders the module's fields and links each sample occurrence to its detail page", async () => {
        getModule.mockResolvedValue({
            hash: "abc",
            id: 1,
            title: "A Song",
            filename: "song.xm",
            tracker: "xm",
            channel_count: 4,
            pattern_count: 2,
            instrument_count: 1,
            sample_count: 1,
            file_size: 4096,
            ingested_at: "2026-01-01T00:00:00Z",
            occurrences: [
                {
                    properties: {
                        sample_hash: "sample-1",
                        occurrence: { module_hash: "abc", instrument_index: 0, sample_slot: 0 },
                        name: "lead",
                        rate: 8363,
                        volume: 64,
                        tracker: "xm",
                        tuning: { relative_note: 0, finetune: 0 },
                    },
                    sample: {
                        hash: "sample-1",
                        depth: 16,
                        channels: 1,
                        frames: 4096,
                        size_bytes: 8192,
                        thumbnail: null,
                    },
                },
            ],
        });

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("heading", { name: "A Song" })).toBeInTheDocument();
        });
        expect(screen.getByRole("link", { name: "lead" })).toHaveAttribute("href", "/samples/sample-1");
        expect(screen.getByText("4.0 KiB")).toBeInTheDocument();
        expect(screen.getByText("8.0 KiB")).toBeInTheDocument();
        expect(screen.getByText("16-bit")).toBeInTheDocument();
    });

    it("falls back to placeholders for an untitled module and an unnamed sample occurrence", async () => {
        getModule.mockResolvedValue({
            hash: "abc",
            id: 1,
            title: "",
            filename: "song.xm",
            tracker: "xm",
            channel_count: 4,
            pattern_count: 2,
            instrument_count: 1,
            sample_count: 1,
            file_size: 0,
            ingested_at: "2026-01-01T00:00:00Z",
            occurrences: [
                {
                    properties: {
                        sample_hash: "sample-1",
                        occurrence: { module_hash: "abc", instrument_index: 0, sample_slot: 0 },
                        name: "",
                        rate: 8363,
                        volume: 64,
                        tracker: "xm",
                        tuning: { relative_note: 0, finetune: 0 },
                    },
                    sample: {
                        hash: "sample-1",
                        depth: 16,
                        channels: 1,
                        frames: 4096,
                        size_bytes: 8192,
                        thumbnail: null,
                    },
                },
            ],
        });

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("heading", { name: "[untitled]" })).toBeInTheDocument();
        });
        expect(screen.getByRole("link", { name: "[unnamed]" })).toHaveAttribute("href", "/samples/sample-1");
    });

    it("shows an error notice when the module cannot be found", async () => {
        getModule.mockRejectedValue(new Error("no module catalogued with hash 'abc'"));

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("no module catalogued with hash 'abc'");
        });
    });
});
