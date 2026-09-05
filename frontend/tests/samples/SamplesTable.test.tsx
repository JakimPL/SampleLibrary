import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { SampleSummary } from "../../src/api/samples";
import { SamplesTable } from "../../src/samples/SamplesTable";

function buildSample(overrides: Pick<SampleSummary, "hash" | "display_name" | "occurrence_count">): SampleSummary {
    return {
        depth: 16,
        channels: 1,
        frames: 4096,
        size_bytes: 8192,
        thumbnail: null,
        ...overrides,
    };
}

const SAMPLES: readonly SampleSummary[] = [
    buildSample({ hash: "a", display_name: "kick", occurrence_count: 3 }),
    buildSample({ hash: "b", display_name: "snare", occurrence_count: 1 }),
    buildSample({ hash: "c", display_name: "hat", occurrence_count: 2 }),
];

function renderTable(
    overrides: Partial<{
        readonly samples: readonly SampleSummary[];
        readonly total: number;
        readonly hasMore: boolean;
        readonly onLoadMore: () => void;
    }> = {},
): ReturnType<typeof render> {
    return render(
        <MemoryRouter>
            <SamplesTable
                samples={overrides.samples ?? SAMPLES}
                total={overrides.total ?? SAMPLES.length}
                hasMore={overrides.hasMore ?? false}
                isLoadingMore={false}
                onLoadMore={overrides.onLoadMore ?? vi.fn()}
                loadMoreError={null}
            />
        </MemoryRouter>,
    );
}

function nameOrder(): string[] {
    return screen.getAllByRole("link").map((link) => link.textContent);
}

describe("SamplesTable", () => {
    it("renders every sample in its given order by default", () => {
        renderTable();

        expect(nameOrder()).toEqual(["kick", "snare", "hat"]);
    });

    it("sorts by a column when its header is clicked, toggling direction on a second click", () => {
        renderTable();

        // Occurrences is a numeric column, and tanstack-table's default is descending-first for
        // numeric data (`getAutoSortDir`), unlike the ascending-first default for text columns.
        fireEvent.click(screen.getByText("Occurrences"));
        expect(nameOrder()).toEqual(["kick", "hat", "snare"]);

        fireEvent.click(screen.getByText("Occurrences"));
        expect(nameOrder()).toEqual(["snare", "hat", "kick"]);
    });

    it("narrows rows to those matching the free-text filter", () => {
        renderTable();

        fireEvent.change(screen.getByPlaceholderText("Filter samples…"), { target: { value: "snare" } });

        expect(nameOrder()).toEqual(["snare"]);
    });

    it("shows how many of the catalog's samples are loaded so far", () => {
        renderTable({ total: 40 });

        expect(screen.getByText(/3 of 40 loaded/)).toBeInTheDocument();
    });

    it("never requests more once there is nothing left to load", () => {
        const onLoadMore = vi.fn();
        renderTable({ onLoadMore, hasMore: false });

        expect(onLoadMore).not.toHaveBeenCalled();
    });

    it("requests more immediately when the loaded rows already fit entirely on screen", () => {
        const onLoadMore = vi.fn();
        renderTable({ onLoadMore, hasMore: true });

        expect(onLoadMore).toHaveBeenCalled();
    });

    it("requests the next window once scrolled near the end of the loaded rows", () => {
        const manySamples = Array.from({ length: 100 }, (_, index) =>
            buildSample({
                hash: `hash-${String(index)}`,
                display_name: `sample-${String(index)}`,
                occurrence_count: 1,
            }),
        );
        const onLoadMore = vi.fn();
        renderTable({ samples: manySamples, total: 200, hasMore: true, onLoadMore });
        expect(onLoadMore).not.toHaveBeenCalled();

        const scrollContainer = document.querySelector(".panel-body");
        if (scrollContainer === null) {
            throw new Error("scroll container not found");
        }
        Object.defineProperty(scrollContainer, "scrollTop", { configurable: true, value: 3000 });
        fireEvent.scroll(scrollContainer);

        expect(onLoadMore).toHaveBeenCalled();
    });
});
