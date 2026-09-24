import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { BuildView, SetupState } from "../../src/api/setup";
import { BuildPanel } from "../../src/setup/BuildPanel";

const RUNNING_BUILD: BuildView = {
    target: "catalog",
    status: "running",
    started_at: "2026-09-24T10:00:00Z",
    ended_at: null,
    steps: [
        { name: "modules", state: "up to date", progress: null },
        {
            name: "thumbnails",
            state: "running",
            progress: { label: "Computing thumbnails", done: 40, total: 160, updated_at: "2026-09-24T10:01:00Z" },
        },
        { name: "equivalence", state: "waiting", progress: null },
    ],
    problem: null,
    log_tail: [],
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

function renderPanel(state: SetupState): void {
    render(
        <MemoryRouter>
            <BuildPanel state={state} onChanged={() => undefined} />
        </MemoryRouter>,
    );
}

describe("BuildPanel", () => {
    it("offers both builds while none runs", () => {
        renderPanel(stateWith(null));

        expect(screen.getByRole("button", { name: "Scan my folders" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Scan and build the cloud" })).toBeInTheDocument();
    });

    it("lists every step in plain words, with the running one's count and a way to cancel", () => {
        renderPanel(stateWith(RUNNING_BUILD));

        expect(screen.getByText("Reading your modules")).toBeInTheDocument();
        expect(screen.getByText("Drawing waveforms")).toBeInTheDocument();
        expect(screen.getByText("40 of 160")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Cancel the build" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Scan my folders" })).not.toBeInTheDocument();
    });

    it("shows the end of a failed step's log", () => {
        renderPanel(
            stateWith({
                ...RUNNING_BUILD,
                status: "failed",
                problem: "The step thumbnails ended as failed.",
                log_tail: ["the disk is full"],
            }),
        );

        expect(screen.getByText("The build stopped")).toBeInTheDocument();
        expect(screen.getByText("the disk is full")).toBeInTheDocument();
    });
});
