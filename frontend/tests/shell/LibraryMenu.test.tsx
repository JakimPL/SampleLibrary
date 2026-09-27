import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as SetupApi from "../../src/api/setup";
import type { SetupState } from "../../src/api/setup";
import { LibraryMenu } from "../../src/shell/LibraryMenu";

const { getSetupState, quitApplication } = vi.hoisted(() => ({ getSetupState: vi.fn(), quitApplication: vi.fn() }));

vi.mock("../../src/api/setup", async () => {
    const actual = await vi.importActual<typeof SetupApi>("../../src/api/setup");
    return { ...actual, getSetupState, quitApplication };
});

const READY: SetupState = {
    status: "ready",
    config_path: "/home/person/.config/SampleLibrary/config.toml",
    sources: {
        library_root: "/home/person/Music/SampleLibrary",
        module_source_directory: "/home/person/Modules",
        sample_directories: [],
        sample_exclusions: [],
    },
    options: { build_cloud: true, open_to_network: false },
    build_device: { card: null },
    suggested_library_root: "/home/person/Music/SampleLibrary",
    manages_database: true,
    problem: null,
    build: null,
    home_network: { open: false, address: null },
};

function renderWorkspace(): void {
    render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<LibraryMenu />} />
                <Route path="/setup" element={<p>The setup page</p>} />
                <Route path="/closed" element={<p>The closed page</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("LibraryMenu", () => {
    it("opens the library's setup where the setup routes answer", async () => {
        getSetupState.mockResolvedValue(READY);
        renderWorkspace();

        fireEvent.click(await screen.findByText("Library"));
        fireEvent.click(screen.getByRole("button", { name: "Setup" }));

        expect(await screen.findByText("The setup page")).toBeInTheDocument();
    });

    it("quits the application and says the tab can close", async () => {
        getSetupState.mockResolvedValue(READY);
        quitApplication.mockResolvedValue(undefined);
        renderWorkspace();

        fireEvent.click(await screen.findByText("Library"));
        fireEvent.click(screen.getByRole("button", { name: "Quit SampleRipper" }));

        expect(await screen.findByText("The closed page")).toBeInTheDocument();
    });

    it("stays away where the setup routes answer no one but the machine the application runs on", async () => {
        getSetupState.mockRejectedValue(new Error("forbidden"));
        renderWorkspace();

        await waitFor(() => {
            expect(getSetupState).toHaveBeenCalled();
        });
        expect(screen.queryByText("Library")).not.toBeInTheDocument();
    });
});
