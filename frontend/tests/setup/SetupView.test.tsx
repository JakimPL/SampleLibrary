import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../src/api/client";
import type * as SetupApi from "../../src/api/setup";
import type { SetupState } from "../../src/api/setup";
import { SetupView } from "../../src/setup/SetupView";

const { getSetupState, getStats, quitApplication } = vi.hoisted(() => ({
    getSetupState: vi.fn(),
    getStats: vi.fn(),
    quitApplication: vi.fn(),
}));

vi.mock("../../src/api/stats", () => ({ getStats }));
vi.mock("../../src/api/setup", async () => {
    const actual = await vi.importActual<typeof SetupApi>("../../src/api/setup");
    return { ...actual, getSetupState, quitApplication };
});

const UNCONFIGURED: SetupState = {
    status: "unconfigured",
    config_path: "/home/person/.config/SampleRipper/config.toml",
    sources: null,
    options: null,
    build_device: { card: null },
    suggested_library_root: "/home/person/Music/SampleRipper",
    manages_database: null,
    problem: null,
    build: null,
    home_network: { open: false, address: null },
};

const NOT_FOUND = 404;

function renderPage(): void {
    render(
        <MemoryRouter initialEntries={["/setup"]}>
            <Routes>
                <Route path="/setup" element={<SetupView />} />
                <Route path="/closed" element={<p>The closed page</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("SetupView", () => {
    it("shows the folders and the library as two panels under the bar, with Quit in its corner", async () => {
        getSetupState.mockResolvedValue(UNCONFIGURED);
        renderPage();

        expect(await screen.findByRole("heading", { name: "Folders" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Library" })).toBeInTheDocument();
        expect(screen.getByLabelText("Theme")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Quit" })).toBeEnabled();
        expect(screen.getByRole("button", { name: "Open the library" })).toBeDisabled();
    });

    it("quits to the closed page", async () => {
        getSetupState.mockResolvedValue(UNCONFIGURED);
        quitApplication.mockResolvedValue(undefined);
        renderPage();

        fireEvent.click(await screen.findByRole("button", { name: "Quit" }));

        expect(await screen.findByText("The closed page")).toBeInTheDocument();
        expect(quitApplication).toHaveBeenCalledOnce();
    });

    it("says in the bar when the application is out of reach", async () => {
        getSetupState.mockRejectedValue(new Error("connection refused"));
        renderPage();

        expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach SampleRipper: connection refused");
        expect(screen.getByRole("button", { name: "Quit" })).toBeDisabled();
    });

    it("explains where setup belongs when the server has no setup routes", async () => {
        getSetupState.mockRejectedValue(new ApiError(NOT_FOUND, "Not Found", null));
        renderPage();

        expect(await screen.findByText("Setup isn't available here")).toBeInTheDocument();
    });
});
