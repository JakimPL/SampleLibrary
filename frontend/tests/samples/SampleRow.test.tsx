import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../src/api/cloud";
import type * as CurationApi from "../../src/api/curation";
import type { SampleSummary } from "../../src/api/samples";
import type { InputMode } from "../../src/layout/layoutMode";
import { type SampleColumnId, sampleColumnSpec } from "../../src/samples/sampleColumns";
import { SampleRow } from "../../src/samples/SampleRow";
import { useAudioPreview } from "../../src/samples/useAudioPreview";
import { LONG_PRESS_HOLD_MS } from "../../src/shared/gestures/gestureThresholds";
import { useSelectionStore } from "../../src/workspace/selectionStore";

const { changeSampleAnnotation, getLabelVocabulary, getCategoryTags } = vi.hoisted(() => ({
    changeSampleAnnotation: vi.fn(),
    getLabelVocabulary: vi.fn(),
    getCategoryTags: vi.fn(),
}));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, changeSampleAnnotation, getLabelVocabulary };
});

vi.mock("../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../src/api/cloud");
    return { ...actual, getCategoryTags };
});

const NOTHING = { label: null, rating: null, favorite: false };

function resolvesTo(annotation: CurationApi.AnnotationDecisions | null): void {
    changeSampleAnnotation.mockResolvedValue({ samples: [{ sample_hash: "abc123", annotation }], skipped: [] });
}

function buildSample(overrides: Partial<SampleSummary> = {}): SampleSummary {
    return {
        hash: "abc123",
        display_name: "kick",
        category: null,
        hand_label: null,
        rating: null,
        favorite: false,
        occurrence_count: 1,
        depth: 16,
        channels: 1,
        frames: 4096,
        size_bytes: 8192,
        thumbnail: null,
        playback_rate_hz: null,
        equivalence_class_hash: null,
        equivalence_member_count: 1,
        ...overrides,
    };
}

const EVERY_COLUMN: ReadonlySet<SampleColumnId> = new Set(sampleColumnSpec("pointer").map((column) => column.id));

interface RowOverrides {
    readonly sample?: SampleSummary;
    readonly groupByEquivalence?: boolean;
    readonly visibleColumns?: ReadonlySet<SampleColumnId>;
    readonly input?: InputMode;
}

function renderRow(overrides: RowOverrides = {}): ReturnType<typeof render> {
    getLabelVocabulary.mockResolvedValue([]);
    getCategoryTags.mockResolvedValue([]);
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route
                    path="/"
                    element={
                        <table>
                            <tbody>
                                <SampleRow
                                    sample={overrides.sample ?? buildSample()}
                                    groupByEquivalence={overrides.groupByEquivalence ?? false}
                                    visibleColumns={overrides.visibleColumns ?? EVERY_COLUMN}
                                    input={overrides.input ?? "pointer"}
                                />
                            </tbody>
                        </table>
                    }
                />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("SampleRow", () => {
    it("a plain click on the name highlights the sample without navigating to its own route", () => {
        renderRow();

        fireEvent.click(screen.getByRole("link", { name: /kick/ }), { detail: 1 });

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "abc123" });
        expect(screen.queryByText("sample route")).not.toBeInTheDocument();
    });

    it("a double-click still navigates to the sample's own route", async () => {
        renderRow();

        fireEvent.doubleClick(screen.getByRole("link", { name: /kick/ }));

        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });

    it("names a sample from the listing itself, without opening it first", async () => {
        resolvesTo({ ...NOTHING, label: "WARM PAD" });
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Edit category" }));
        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad{Enter}");

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { label: "warm pad" });
        });
    });

    it("takes a hand label back when the field is emptied, leaving what the model heard showing", async () => {
        resolvesTo(null);
        renderRow({ sample: buildSample({ category: "SYNTH: PAD", hand_label: "warm pad" }) });

        await userEvent.click(screen.getByRole("button", { name: "Edit category" }));
        await userEvent.clear(screen.getByLabelText("Hand label"));
        await userEvent.keyboard("{Enter}");

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { label: null });
        });
        expect(await screen.findByText("SYNTH: PAD")).toBeInTheDocument();
    });

    it("rates a sample from the listing by sending the rating alone", async () => {
        resolvesTo({ label: "WARM PAD", rating: 4, favorite: false });
        renderRow({ sample: buildSample({ hand_label: "WARM PAD" }) });

        await userEvent.click(screen.getByRole("button", { name: "Rate 4" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { rating: 4 });
        });
    });

    it("marks a favorite from the listing", async () => {
        resolvesTo({ ...NOTHING, favorite: true });
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Favorite" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { favorite: true });
        });
    });

    it("reaches every near-duplicate while the listing groups them", async () => {
        resolvesTo({ ...NOTHING, rating: 2 });
        renderRow({ sample: buildSample({ equivalence_member_count: 3 }), groupByEquivalence: true });

        await userEvent.click(screen.getByRole("button", { name: "Rate 2" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "equivalence_class", { rating: 2 });
        });
    });

    it("says in the row when a change could not be saved", async () => {
        changeSampleAnnotation.mockRejectedValue(new Error("request failed with status 500"));
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Rate 3" }));

        expect(await screen.findByRole("alert")).toHaveAttribute("title", "request failed with status 500");
        expect(screen.getByRole("button", { name: "Rate 3" })).toHaveAttribute("aria-pressed", "false");
    });

    it("sends a label and a star given in quick succession one after the other, each naming its own decision", async () => {
        let answerLabel: (written: CurationApi.AnnotationsWritten) => void = () => undefined;
        changeSampleAnnotation
            .mockImplementationOnce(
                () =>
                    new Promise<CurationApi.AnnotationsWritten>((resolve) => {
                        answerLabel = resolve;
                    }),
            )
            .mockResolvedValueOnce({
                samples: [{ sample_hash: "abc123", annotation: { label: "BASS", rating: 5, favorite: false } }],
                skipped: [],
            });
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Edit category" }));
        await userEvent.type(screen.getByLabelText("Hand label"), "bass{Enter}");
        await userEvent.click(screen.getByRole("button", { name: "Rate 5" }));

        expect(changeSampleAnnotation).toHaveBeenCalledTimes(1);
        answerLabel({
            samples: [{ sample_hash: "abc123", annotation: { label: "BASS", rating: null, favorite: false } }],
            skipped: [],
        });

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenLastCalledWith("abc123", "sample", { rating: 5 });
        });
        expect(await screen.findByText("BASS")).toBeInTheDocument();
    });

    it("names the category beneath the name once the category column has left", () => {
        const withoutCategory = new Set([...EVERY_COLUMN].filter((id) => id !== "category"));
        renderRow({ sample: buildSample({ category: "SYNTH: PAD" }), visibleColumns: withoutCategory });

        expect(screen.getByRole("link", { name: /kick/ })).toHaveTextContent("SYNTH: PAD");
        expect(screen.queryByRole("button", { name: "Edit category" })).not.toBeInTheDocument();
        expect(screen.queryByText("abc123")).not.toBeInTheDocument();
    });

    it("keeps the heart alone in the verdict column under touch", () => {
        renderRow({ input: "touch" });

        expect(screen.getByRole("button", { name: "Favorite" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Rate 3" })).not.toBeInTheDocument();
    });

    it("plays the sample on the space bar, rates it on a digit and marks it on F while its link is focused", async () => {
        resolvesTo({ ...NOTHING, rating: 3 });
        renderRow();
        const link = screen.getByRole("link", { name: /kick/ });
        const { result } = renderHook(() => useAudioPreview());

        fireEvent.keyDown(link, { key: " " });
        expect(result.current.playingKey).toBe("abc123");

        fireEvent.keyDown(link, { key: "3" });
        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { rating: 3 });
        });

        fireEvent.keyDown(link, { key: "f" });
        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { favorite: true });
        });
    });

    it("offers the row's chevron as the way to open it", () => {
        renderRow();

        expect(screen.getByRole("link", { name: "Open sample" })).toHaveAttribute("href", "/samples/abc123");
    });

    describe("under touch", () => {
        afterEach(() => {
            vi.useRealTimers();
        });

        it("opens the actions sheet on a held finger", () => {
            vi.useFakeTimers();
            renderRow({ input: "touch" });
            const row = screen.getByRole("link", { name: /kick/ }).closest("tr");
            if (row === null) {
                throw new Error("the row is missing");
            }

            fireEvent.pointerDown(row, { pointerId: 1, pointerType: "touch", clientX: 10, clientY: 10 });
            act(() => {
                vi.advanceTimersByTime(LONG_PRESS_HOLD_MS);
            });

            expect(screen.getByRole("dialog", { name: "kick" })).toBeInTheDocument();
        });

        it("opens the label sheet from the category badge", () => {
            renderRow({ input: "touch" });

            fireEvent.click(screen.getByRole("button", { name: "Edit category" }));

            expect(screen.getByRole("dialog", { name: "Label" })).toBeInTheDocument();
        });

        it("takes the sample in hand and plays it on a tap", () => {
            renderRow({ input: "touch" });
            const { result } = renderHook(() => useAudioPreview());
            act(() => {
                result.current.stop();
            });

            fireEvent.click(screen.getByRole("link", { name: /kick/ }), { detail: 1 });

            expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "abc123" });
            expect(result.current.playingKey).toBe("abc123");
        });

        it("leaves the sound alone when the tap is the heart's own", () => {
            renderRow({ input: "touch" });
            const { result } = renderHook(() => useAudioPreview());
            act(() => {
                result.current.stop();
            });

            fireEvent.click(screen.getByRole("button", { name: "Favorite" }), { detail: 1 });

            expect(result.current.playingKey).toBeNull();
        });
    });

    it("fills the heart under the pointer, showing what the click would leave behind", async () => {
        renderRow();

        await userEvent.hover(screen.getByRole("button", { name: "Favorite" }));

        expect(screen.getByRole("button", { name: "Favorite" })).toHaveClass("is-filled");
        expect(screen.getByRole("button", { name: "Favorite" })).toHaveAttribute("aria-pressed", "false");
    });

    it("fills every star up to the one being pointed at", async () => {
        renderRow();

        await userEvent.hover(screen.getByRole("button", { name: "Rate 4" }));

        expect(screen.getByRole("button", { name: "Rate 1" })).toHaveClass("is-filled");
        expect(screen.getByRole("button", { name: "Rate 4" })).toHaveClass("is-filled");
        expect(screen.getByRole("button", { name: "Rate 5" })).not.toHaveClass("is-filled");
    });
});
