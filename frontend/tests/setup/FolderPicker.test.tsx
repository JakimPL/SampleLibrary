import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as SetupApi from "../../src/api/setup";
import type { FolderListing } from "../../src/api/setup";
import { FolderPicker } from "../../src/setup/FolderPicker";

const { getFolder, getPlaces } = vi.hoisted(() => ({ getFolder: vi.fn(), getPlaces: vi.fn() }));

vi.mock("../../src/api/setup", async () => {
    const actual = await vi.importActual<typeof SetupApi>("../../src/api/setup");
    return { ...actual, getFolder, getPlaces };
});

const MODULES: FolderListing = {
    path: "/home/person/Modules",
    parent: "/home/person",
    folders: [{ name: "Chiptune", path: "/home/person/Modules/Chiptune" }],
    module_files: 12,
    audio_files: 0,
};

describe("FolderPicker", () => {
    it("keeps its buttons while a folder loads, and takes the folder once it has", async () => {
        let answer: (listing: FolderListing) => void = () => undefined;
        getPlaces.mockResolvedValue([{ name: "Home", path: "/home/person" }]);
        getFolder.mockReturnValue(
            new Promise<FolderListing>((resolve) => {
                answer = resolve;
            }),
        );
        const onChoose = vi.fn();
        render(
            <FolderPicker title="Choose" initialPath="/home/person/Modules" onChoose={onChoose} onClose={vi.fn()} />,
        );

        expect(screen.getByText("Loading…")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Choose this folder" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();

        answer(MODULES);

        expect(await screen.findByText(/12 modules/)).toBeInTheDocument();
        screen.getByRole("button", { name: "Choose this folder" }).click();
        expect(onChoose).toHaveBeenCalledWith("/home/person/Modules");
    });
});
