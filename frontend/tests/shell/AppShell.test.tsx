import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { PHONE_MEDIA_QUERY } from "../../src/layout/layoutMode";
import { useMorphStore } from "../../src/morph/morphStore";
import type { ShellView } from "../../src/navigation/shellView";
import { AppShell } from "../../src/shell/AppShell";
import { useSelectionStore } from "../../src/workspace/selectionStore";
import { stubMatchMedia } from "../support/matchMedia";
import { choosePair } from "../support/morphPair";

vi.mock("../../src/workspace/WorkspaceShell", () => ({
    WorkspaceShell: ({ view }: { view: ShellView }) => <p>{JSON.stringify(view)}</p>,
}));

vi.mock("../../src/shell/phone/PhoneShell", () => ({
    PhoneShell: ({ view }: { view: ShellView }) => <p>phone {JSON.stringify(view)}</p>,
}));

describe("AppShell", () => {
    it("hands a panel view to the shell as the route names it", () => {
        render(
            <MemoryRouter initialEntries={["/cloud"]}>
                <Routes>
                    <Route path="/cloud" element={<AppShell routeView={{ kind: "panel", panelId: "cloud" }} />} />
                </Routes>
            </MemoryRouter>,
        );

        expect(screen.getByText(JSON.stringify({ kind: "panel", panelId: "cloud" }))).toBeInTheDocument();
    });

    it("completes an entity view from the address and focuses it", () => {
        render(
            <MemoryRouter initialEntries={["/samples/abc"]}>
                <Routes>
                    <Route path="/samples/:sampleHash" element={<AppShell routeView={{ kind: "sample" }} />} />
                </Routes>
            </MemoryRouter>,
        );

        expect(screen.getByText(JSON.stringify({ kind: "sample", sampleHash: "abc" }))).toBeInTheDocument();
        expect(useSelectionStore.getState().focusedSampleHash).toBe("abc");
    });

    it("mounts the phone shell where the viewport asks for it", () => {
        stubMatchMedia(new Set([PHONE_MEDIA_QUERY]));

        render(
            <MemoryRouter initialEntries={["/cloud"]}>
                <Routes>
                    <Route path="/cloud" element={<AppShell routeView={{ kind: "panel", panelId: "cloud" }} />} />
                </Routes>
            </MemoryRouter>,
        );

        expect(screen.getByText(`phone ${JSON.stringify({ kind: "panel", panelId: "cloud" })}`)).toBeInTheDocument();
    });

    it("undoes the morph's last change from a key on any address", () => {
        choosePair("a", "b");
        useMorphStore.getState().setEnd("second", "c");
        render(
            <MemoryRouter initialEntries={["/modules"]}>
                <Routes>
                    <Route
                        path="/modules"
                        element={<AppShell routeView={{ kind: "panel", panelId: "modules-list" }} />}
                    />
                </Routes>
            </MemoryRouter>,
        );

        fireEvent.keyDown(window, { key: "z", ctrlKey: true });

        expect(useMorphStore.getState()).toMatchObject({ first: "a", second: "b" });
    });
});
