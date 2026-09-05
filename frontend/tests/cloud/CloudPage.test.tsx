import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../src/api/cloud";
import { CloudPage } from "../../src/cloud/CloudPage";

const { getCloud } = vi.hoisted(() => ({ getCloud: vi.fn() }));

vi.mock("../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../src/api/cloud");
    return { ...actual, getCloud };
});

function renderPage(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/cloud"]}>
            <Routes>
                <Route path="/cloud" element={<CloudPage />} />
                <Route path="/samples/:sampleHash" element={<p>sample detail page</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("CloudPage", () => {
    it("shows a loading state before the points arrive", () => {
        getCloud.mockReturnValue(new Promise(() => undefined));

        renderPage();

        expect(screen.getByText("Loading…")).toBeInTheDocument();
    });

    it("renders a canvas once the points have loaded", async () => {
        getCloud.mockResolvedValue([{ sample_hash: "a".repeat(64), x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]);

        renderPage();

        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });
    });

    it("shows an error notice when the request fails", async () => {
        getCloud.mockRejectedValue(new Error("service unavailable"));

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("service unavailable");
        });
    });

    it("navigates to the nearest sample when the canvas is clicked close to it", async () => {
        const sampleHash = "b".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]);
        renderPage();
        const canvas = await waitFor(() => {
            const element = document.querySelector("canvas");
            if (element === null) {
                throw new Error("canvas not found");
            }
            return element;
        });

        fireEvent.click(canvas, { offsetX: 0, offsetY: 0 });

        await waitFor(() => {
            expect(screen.getByText("sample detail page")).toBeInTheDocument();
        });
    });
});
