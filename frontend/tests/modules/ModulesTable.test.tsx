import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Module } from "../../src/api/modules";
import { ModulesTable } from "../../src/modules/ModulesTable";
import { useListingOrderStore } from "../../src/workspace/listingOrderStore";
import { ROW_LINK_ATTRIBUTE } from "../../src/workspace/rowLinks";
import { useSelectionStore } from "../../src/workspace/selectionStore";

const PAGE_URL = "https://www.modules.pl/?id=module&mod=9752";

function buildModule(
    overrides: Pick<Module, "hash" | "id" | "title" | "tracker" | "file_size"> & Partial<Pick<Module, "link">>,
): Module {
    return {
        filename: `${overrides.title}.${overrides.tracker}`,
        channel_count: 4,
        pattern_count: 1,
        instrument_count: 1,
        sample_count: 1,
        ingested_at: "2026-01-01T00:00:00Z",
        link: null,
        ...overrides,
    };
}

const MODULES: readonly Module[] = [
    buildModule({ hash: "a", id: 1, title: "Zeta", tracker: "xm", file_size: 3000 }),
    buildModule({ hash: "b", id: 2, title: "Alpha", tracker: "it", file_size: 1000, link: PAGE_URL }),
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
    return Array.from(document.querySelectorAll("a.cell-name-stack")).map(
        (link) => link.querySelector(".cell-primary")?.textContent ?? "",
    );
}

describe("ModulesTable", () => {
    it("renders every module in its given order by default", () => {
        renderTable();

        expect(titleOrder()).toEqual(["Zeta", "Alpha", "Mid"]);
    });

    it("publishes the order of the rows it shows, following a sort", () => {
        renderTable();
        expect(useListingOrderStore.getState().orderByKind.module).toEqual(["a", "b", "c"]);

        fireEvent.click(screen.getByText("Title"));

        expect(useListingOrderStore.getState().orderByKind.module).toEqual(["b", "c", "a"]);
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

    it("keeps the title while the other columns leave in a narrow panel", () => {
        vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
            x: 0,
            y: 0,
            width: 160,
            height: 600,
            top: 0,
            right: 160,
            bottom: 600,
            left: 0,
            toJSON: () => ({}),
        });

        const { container } = renderTable();

        expect(container.querySelectorAll("thead th")).toHaveLength(2);
        expect(screen.getAllByText("xm")).toHaveLength(2);
    });

    it("offers a module's page at the end of its row, as a link the row's own click rule lets through", () => {
        renderTable();

        const link = screen.getByRole("link", { name: /modules\.pl/ });

        expect(link).toHaveAttribute("href", PAGE_URL);
        expect(link).toHaveAttribute("target", "_blank");
        expect(link.getAttribute("rel")).toContain("noreferrer");
        expect(link).toHaveAttribute(ROW_LINK_ATTRIBUTE);
        expect(document.querySelectorAll("td.cell-link a")).toHaveLength(1);
    });

    it("keeps a double click on the page link from opening the module", () => {
        render(
            <MemoryRouter initialEntries={["/"]}>
                <Routes>
                    <Route path="/" element={<ModulesTable modules={MODULES} />} />
                    <Route path="/modules/:moduleHash" element={<p>module route</p>} />
                </Routes>
            </MemoryRouter>,
        );

        fireEvent.doubleClick(screen.getByRole("link", { name: /modules\.pl/ }));

        expect(screen.queryByText("module route")).toBeNull();
        expect(useSelectionStore.getState().highlighted).toBeNull();
    });

    it("narrows rows to the selected tracker", () => {
        renderTable();

        fireEvent.change(screen.getByLabelText("Tracker"), { target: { value: "it" } });

        expect(titleOrder()).toEqual(["Alpha"]);
    });
});
