import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../src/api/samples";
import { SampleListPage } from "../../src/samples/SampleListPage";

const { listSamples } = vi.hoisted(() => ({ listSamples: vi.fn() }));

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, listSamples };
});

function renderPage(): ReturnType<typeof render> {
    return render(
        <MemoryRouter>
            <SampleListPage />
        </MemoryRouter>,
    );
}

describe("SampleListPage", () => {
    it("shows a loading state before the samples arrive", () => {
        listSamples.mockReturnValue(new Promise(() => undefined));

        renderPage();

        expect(screen.getByText("Loading…")).toBeInTheDocument();
    });

    it("renders the fetched samples once loaded", async () => {
        listSamples.mockResolvedValue({
            items: [
                {
                    hash: "abc",
                    depth: 16,
                    channels: 1,
                    frames: 4096,
                    occurrence_count: 3,
                    display_name: "kick",
                    size_bytes: 8192,
                },
            ],
            total: 1,
            limit: 50,
            offset: 0,
        });

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("link", { name: "kick" })).toHaveAttribute("href", "/samples/abc");
        });
        expect(screen.getByText("3")).toBeInTheDocument();
        expect(screen.getByText("8.0 KiB")).toBeInTheDocument();
    });

    it("links a sample with an empty display name through the [unnamed] placeholder", async () => {
        listSamples.mockResolvedValue({
            items: [
                {
                    hash: "abc",
                    depth: 16,
                    channels: 1,
                    frames: 4096,
                    occurrence_count: 0,
                    display_name: "",
                    size_bytes: 0,
                },
            ],
            total: 1,
            limit: 50,
            offset: 0,
        });

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("link", { name: "[unnamed]" })).toHaveAttribute("href", "/samples/abc");
        });
    });

    it("shows an error notice when the request fails", async () => {
        listSamples.mockRejectedValue(new Error("network down"));

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("network down");
        });
    });
});
