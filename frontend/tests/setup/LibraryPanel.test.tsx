import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as SetupApi from "../../src/api/setup";
import type { BuildDevice, BuildView, HomeNetworkReach, SetupState } from "../../src/api/setup";
import type { LibraryStats } from "../../src/api/stats";
import { LibraryPanel } from "../../src/setup/LibraryPanel";

const { getStats, startBuild, chooseOptions } = vi.hoisted(() => ({
    getStats: vi.fn(),
    startBuild: vi.fn(),
    chooseOptions: vi.fn(),
}));

vi.mock("../../src/api/stats", () => ({ getStats }));
vi.mock("../../src/api/setup", async () => {
    const actual = await vi.importActual<typeof SetupApi>("../../src/api/setup");
    return { ...actual, startBuild, chooseOptions };
});

const CARD: BuildDevice = { card: "NVIDIA GeForce RTX 5070 Ti" };
const PROCESSOR: BuildDevice = { card: null };

const LIBRARY_STATS: LibraryStats = {
    module_count: 30,
    sample_count: 300,
    sample_properties_count: 300,
    sample_file_count: 0,
    modules_by_tracker: [],
    relations_by_type: [],
    total_stored_bytes: 0,
};

const RUNNING_BUILD: BuildView = {
    target: "catalog",
    status: "running",
    started_at: "2026-09-24T10:00:00Z",
    ended_at: null,
    steps: [
        { name: "modules", state: "up to date", started_at: null, ended_at: null, progress: null },
        {
            name: "thumbnails",
            state: "running",
            started_at: "2026-09-24T10:00:30Z",
            ended_at: null,
            progress: {
                label: "Computing thumbnails",
                done: 40,
                total: 160,
                resumed: 0,
                started_at: "2026-09-24T10:00:30Z",
                updated_at: "2026-09-24T10:01:00Z",
            },
        },
        { name: "equivalence", state: "waiting", started_at: null, ended_at: null, progress: null },
    ],
    problem: null,
    log_tail: [],
};

const FINISHED_BUILD: BuildView = {
    ...RUNNING_BUILD,
    status: "completed",
    ended_at: "2026-09-24T10:05:00Z",
    steps: [
        {
            name: "thumbnails",
            state: "done",
            started_at: "2026-09-24T10:00:00Z",
            ended_at: "2026-09-24T10:02:30Z",
            progress: null,
        },
    ],
};

const CLOSED_TO_THE_NETWORK: HomeNetworkReach = { open: false, address: null };
const OPEN_TO_THE_NETWORK: HomeNetworkReach = { open: true, address: "http://192.168.1.10:27440/" };

function stateWith(
    build: BuildView | null,
    device: BuildDevice | null = CARD,
    buildCloud = true,
    openToNetwork = false,
    homeNetwork: HomeNetworkReach = CLOSED_TO_THE_NETWORK,
): SetupState {
    return {
        status: "ready",
        config_path: "/home/person/.config/SampleLibrary/config.toml",
        sources: {
            library_root: "/home/person/Music/SampleLibrary",
            module_source_directory: "/home/person/Modules",
            sample_directories: [],
            sample_exclusions: [],
        },
        options: { build_cloud: buildCloud, open_to_network: openToNetwork },
        build_device: device,
        suggested_library_root: "/home/person/Music/SampleLibrary",
        manages_database: true,
        problem: null,
        build,
        home_network: homeNetwork,
    };
}

function renderPanel(state: SetupState, unsavedChanges = false): void {
    getStats.mockResolvedValue(LIBRARY_STATS);
    startBuild.mockResolvedValue(state);
    chooseOptions.mockResolvedValue(state);
    render(<LibraryPanel state={state} unsavedChanges={unsavedChanges} onChanged={() => undefined} />);
}

describe("LibraryPanel", () => {
    it("offers the build with its cloud, names the card, and reports the library's size", async () => {
        renderPanel(stateWith(null));

        expect(screen.getByRole("button", { name: "Build my library" })).toBeEnabled();
        expect(screen.getByRole("checkbox", { name: /Build the cloud/ })).toBeChecked();
        expect(screen.getByText("Builds use your NVIDIA GeForce RTX 5070 Ti.")).toBeInTheDocument();
        expect(await screen.findByText("Your library holds 300 samples and 30 modules.")).toBeInTheDocument();
    });

    it("builds the cloud at once on a card", () => {
        renderPanel(stateWith(null));

        fireEvent.click(screen.getByRole("button", { name: "Build my library" }));

        expect(startBuild).toHaveBeenCalledWith("all");
    });

    it("asks before building the cloud on the processor, and takes the answer", () => {
        renderPanel(stateWith(null, PROCESSOR));

        fireEvent.click(screen.getByRole("button", { name: "Build my library" }));

        expect(startBuild).not.toHaveBeenCalled();
        expect(screen.getByRole("dialog", { name: "Build the cloud without an NVIDIA graphics card?" })).toBeVisible();
        fireEvent.click(screen.getByRole("button", { name: "Build without the cloud" }));
        expect(startBuild).toHaveBeenCalledWith("catalog");
    });

    it("builds the catalog alone once the cloud is switched off, asking nothing", () => {
        renderPanel(stateWith(null, PROCESSOR, false));

        fireEvent.click(screen.getByRole("button", { name: "Build my library" }));

        expect(startBuild).toHaveBeenCalledWith("catalog");
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("saves the cloud switch for the library", () => {
        renderPanel(stateWith(null));

        fireEvent.click(screen.getByRole("checkbox", { name: /Build the cloud/ }));

        expect(chooseOptions).toHaveBeenCalledWith({ build_cloud: false, open_to_network: false });
    });

    it("saves the network switch for the next start, and says a restart applies it", () => {
        renderPanel(stateWith(null));

        expect(screen.queryByText("Restart SampleRipper to apply this.")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("checkbox", { name: /Open on my home network/ }));

        expect(chooseOptions).toHaveBeenCalledWith({ build_cloud: true, open_to_network: true });
    });

    it("says a restart is due while the switch differs from how the library started", () => {
        renderPanel(stateWith(null, CARD, true, true, CLOSED_TO_THE_NETWORK));

        expect(screen.getByRole("checkbox", { name: /Open on my home network/ })).toBeChecked();
        expect(screen.getByText("Restart SampleRipper to apply this.")).toBeInTheDocument();
    });

    it("names the address a device on the network opens", () => {
        renderPanel(stateWith(null, CARD, true, true, OPEN_TO_THE_NETWORK));

        expect(screen.getByText("On another device, open http://192.168.1.10:27440/")).toBeInTheDocument();
    });

    it("waits to build until it knows the device", () => {
        renderPanel(stateWith(null, null));

        expect(screen.getByRole("button", { name: "Build my library" })).toBeDisabled();
        expect(screen.getByText("Checking for an NVIDIA graphics card…")).toBeInTheDocument();
    });

    it("keeps the build in place while one runs, with the running step's count, estimate and a way to cancel", () => {
        renderPanel(stateWith(RUNNING_BUILD));

        expect(screen.getByRole("button", { name: "Build my library" })).toBeDisabled();
        expect(screen.getByRole("checkbox", { name: /Build the cloud/ })).toBeDisabled();
        expect(screen.getByText("Reading your modules")).toBeInTheDocument();
        expect(screen.getByText("40 of 160 · about 2 min left")).toBeInTheDocument();
        expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    });

    it("holds the builds back while the folders have unsaved changes", () => {
        renderPanel(stateWith(null), true);

        expect(screen.getByText("Save your folder changes first.")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Build my library" })).toBeDisabled();
    });

    it("shows how long the build and each of its steps took", () => {
        renderPanel(stateWith(FINISHED_BUILD));

        expect(screen.getByText("Took 5 min")).toBeInTheDocument();
        expect(screen.getByText("took 2 min")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    });

    it("shows the end of a failed step's log", () => {
        renderPanel(
            stateWith({
                ...RUNNING_BUILD,
                status: "failed",
                problem: "Step 'thumbnails' ended: failed.",
                log_tail: ["the disk is full"],
            }),
        );

        expect(screen.getByText("The build stopped")).toBeInTheDocument();
        expect(screen.getByText("the disk is full")).toBeInTheDocument();
    });
});
