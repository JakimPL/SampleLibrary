import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ShellView } from "../../src/navigation/shellView";
import { AppShell } from "../../src/shell/AppShell";
import { useSelectionStore } from "../../src/workspace/selectionStore";

vi.mock("../../src/workspace/WorkspaceShell", () => ({
    WorkspaceShell: ({ view }: { view: ShellView }) => <p>{JSON.stringify(view)}</p>,
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
});
