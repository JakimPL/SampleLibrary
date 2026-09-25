import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BuildView, SetupState } from "../../src/api/setup";
import type { LibraryStats } from "../../src/api/stats";
import { LibraryPanel } from "../../src/setup/LibraryPanel";

const { getStats } = vi.hoisted(() => ({ getStats: vi.fn() }));

vi.mock("../../src/api/stats", () => ({ getStats }));

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

function stateWith(build: BuildView | null): SetupState {
    return {
        status: "ready",
        config_path: "/home/person/.config/SampleLibrary/config.toml",
        sources: {
            library_root: "/home/person/Music/SampleLibrary",
            module_source_directory: "/home/person/Modules",
            sample_directories: [],
            sample_exclusions: [],
        },
        suggested_library_root: "/home/person/Music/SampleLibrary",
        manages_database: true,
        problem: null,
        build,
    };
}

function renderPanel(state: SetupState, unsavedChanges = false): void {
    getStats.mockResolvedValue(LIBRARY_STATS);
    render(<LibraryPanel state={state} unsavedChanges={unsavedChanges} onChanged={() => undefined} />);
}

describe("LibraryPanel", () => {
    it("offers both builds while none runs, and reports the library's size", async () => {
        renderPanel(stateWith(null));

        expect(screen.getByRole("button", { name: "Scan my folders" })).toBeEnabled();
        expect(screen.getByRole("button", { name: "Scan and build the cloud" })).toBeEnabled();
        expect(await screen.findByText("Your library holds 300 samples and 30 modules.")).toBeInTheDocument();
    });

    it("keeps both builds in place while one runs, with the running step's count, estimate and a way to cancel", () => {
        renderPanel(stateWith(RUNNING_BUILD));

        expect(screen.getByRole("button", { name: "Scan my folders" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Scan and build the cloud" })).toBeDisabled();
        expect(screen.getByText("Reading your modules")).toBeInTheDocument();
        expect(screen.getByText("40 of 160 · about 2 min left")).toBeInTheDocument();
        expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    });

    it("holds the builds back while the folders have unsaved changes", () => {
        renderPanel(stateWith(null), true);

        expect(screen.getByText("Save your folder changes first.")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Scan my folders" })).toBeDisabled();
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
