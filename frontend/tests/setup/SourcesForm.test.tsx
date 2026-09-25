import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";

import type { SetupState } from "../../src/api/setup";
import { SourcesForm } from "../../src/setup/SourcesForm";
import { useSourcesDraft } from "../../src/setup/useSourcesDraft";

const UNCONFIGURED: SetupState = {
    status: "unconfigured",
    config_path: "/home/person/.config/SampleLibrary/config.toml",
    sources: null,
    suggested_library_root: "/home/person/Music/SampleLibrary",
    manages_database: null,
    problem: null,
    build: null,
};

const CONFIGURED: SetupState = {
    ...UNCONFIGURED,
    status: "ready",
    sources: {
        library_root: "/data/library",
        module_source_directory: "/data/modules",
        sample_directories: ["/data/packs"],
        sample_exclusions: ["*loop*"],
    },
};

function Form({ state }: { readonly state: SetupState }): ReactElement {
    const draft = useSourcesDraft(state);
    return <SourcesForm state={state} draft={draft} onSaved={() => undefined} />;
}

describe("SourcesForm", () => {
    it("suggests a library location and holds the save back until a folder is chosen", () => {
        render(<Form state={UNCONFIGURED} />);

        expect(screen.getByText("/home/person/Music/SampleLibrary")).toBeInTheDocument();
        expect(screen.getByText("No folder chosen")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Remove" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Save and open the library" })).toBeDisabled();
        expect(screen.getByText("Choose at least one folder first.")).toBeInTheDocument();
    });

    it("shows the folders a library already reads and offers to save once one changes", () => {
        render(<Form state={CONFIGURED} />);

        expect(screen.getByText("/data/modules")).toBeInTheDocument();
        expect(screen.getByText("/data/packs")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

        fireEvent.change(screen.getByDisplayValue("*loop*"), { target: { value: "*loop*, *.aif" } });

        expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    });

    it("keeps the folders as they are while a build runs", () => {
        const building: SetupState = {
            ...CONFIGURED,
            build: {
                target: "catalog",
                status: "running",
                started_at: "2026-09-24T10:00:00Z",
                ended_at: null,
                steps: [],
                problem: null,
                log_tail: [],
            },
        };
        render(<Form state={building} />);

        fireEvent.change(screen.getByDisplayValue("*loop*"), { target: { value: "*loop*, *.aif" } });

        expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
        expect(screen.getByText("Wait for the build to finish or cancel it.")).toBeInTheDocument();
    });
});
