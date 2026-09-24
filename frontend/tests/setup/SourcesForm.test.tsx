import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SetupState } from "../../src/api/setup";
import { SourcesForm } from "../../src/setup/SourcesForm";

const UNCONFIGURED: SetupState = {
    status: "unconfigured",
    config_path: "/home/person/.config/SampleLibrary/config.toml",
    sources: null,
    suggested_library_root: "/home/person/Music/SampleLibrary",
    manages_database: null,
    problem: null,
    build: null,
};

describe("SourcesForm", () => {
    it("suggests a library location and holds the save back until a folder is chosen", () => {
        render(<SourcesForm state={UNCONFIGURED} onSaved={() => undefined} />);

        expect(screen.getByText("/home/person/Music/SampleLibrary")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Save and open the library" })).toBeDisabled();
    });

    it("shows the folders a library already reads and offers to save once one changes", () => {
        render(
            <SourcesForm
                state={{
                    ...UNCONFIGURED,
                    status: "ready",
                    sources: {
                        library_root: "/data/library",
                        module_source_directory: "/data/modules",
                        sample_directories: ["/data/packs"],
                        sample_exclusions: ["*loop*"],
                    },
                }}
                onSaved={() => undefined}
            />,
        );

        expect(screen.getByText("/data/modules")).toBeInTheDocument();
        expect(screen.getByText("/data/packs")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

        fireEvent.change(screen.getByDisplayValue("*loop*"), { target: { value: "*loop*, *.aif" } });

        expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    });
});
