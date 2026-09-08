import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Module } from "../../src/api/modules";
import { ModulesTable } from "../../src/modules/ModulesTable";

function buildModule(overrides: Pick<Module, "hash" | "id" | "title" | "tracker" | "file_size">): Module {
    return {
        filename: `${overrides.title}.${overrides.tracker}`,
        channel_count: 4,
        pattern_count: 1,
        instrument_count: 1,
        sample_count: 1,
        ingested_at: "2026-01-01T00:00:00Z",
        ...overrides,
    };
}

const MODULES: readonly Module[] = [
    buildModule({ hash: "a", id: 1, title: "Zeta", tracker: "xm", file_size: 3000 }),
    buildModule({ hash: "b", id: 2, title: "Alpha", tracker: "it", file_size: 1000 }),
    buildModule({ hash: "c", id: 3, title: "Mid", tracker: "xm", file_size: 2000 }),
];

function renderTable(): ReturnType<typeof render> {
    return render(
        <MemoryRouter>
            <ModulesTable modules={MODULES} />
        </MemoryRouter>,
    );
}

function titleOrder(): string[] {
    return screen.getAllByRole("link").map((link) => link.querySelector(".cell-primary")?.textContent ?? "");
}

describe("ModulesTable", () => {
    it("renders every module in its given order by default", () => {
        renderTable();

        expect(titleOrder()).toEqual(["Zeta", "Alpha", "Mid"]);
    });

    it("sorts by a column when its header is clicked, toggling direction on a second click", () => {
        renderTable();

        fireEvent.click(screen.getByText("Title"));
        expect(titleOrder()).toEqual(["Alpha", "Mid", "Zeta"]);

        fireEvent.click(screen.getByText("Title"));
        expect(titleOrder()).toEqual(["Zeta", "Mid", "Alpha"]);
    });

    it("narrows rows to those matching the free-text filter", () => {
        renderTable();

        fireEvent.change(screen.getByPlaceholderText("Filter modules…"), { target: { value: "alpha" } });

        expect(titleOrder()).toEqual(["Alpha"]);
    });

    it("shows each module's own short hash beneath its title", () => {
        renderTable();

        expect(screen.getByText("a")).toBeInTheDocument();
        expect(screen.getByText("b")).toBeInTheDocument();
        expect(screen.getByText("c")).toBeInTheDocument();
    });

    it("narrows rows to the selected tracker", () => {
        renderTable();

        fireEvent.change(screen.getByLabelText("Tracker"), { target: { value: "it" } });

        expect(titleOrder()).toEqual(["Alpha"]);
    });
});
