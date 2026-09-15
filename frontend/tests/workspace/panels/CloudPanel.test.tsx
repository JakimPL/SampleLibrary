import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../../src/api/cloud";
import type * as ModulesApi from "../../../src/api/modules";
import type * as MorphApi from "../../../src/api/morph";
import type * as SamplesApi from "../../../src/api/samples";
import { useMorphStore } from "../../../src/morph/morphStore";
import type * as AudioPreview from "../../../src/samples/useAudioPreview";
import { CloudPanel } from "../../../src/workspace/panels/CloudPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const {
    instances,
    createScatterplotMock,
    getCloud,
    getModuleCloud,
    getCloudSuggestions,
    getSuggestionTags,
    getSamplePreview,
    getModule,
    getMorphStatus,
    play,
} = vi.hoisted(() => {
    class FakeScatterplot {
        readonly draw = vi.fn().mockResolvedValue(undefined);
        readonly select = vi.fn();
        readonly deselect = vi.fn();
        readonly destroy = vi.fn();
        readonly set = vi.fn().mockResolvedValue(undefined);
        readonly getScreenPosition = vi.fn((index: number) => [10 + index, 20 + index] as [number, number]);
        readonly get = vi.fn((property: string) =>
            property === "cameraView" ? new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]) : undefined,
        );
        private readonly listeners = new Map<string, ((payload: unknown) => void)[]>();

        subscribe(event: string, handler: (payload: unknown) => void): { event: string; handler: unknown } {
            const handlers = this.listeners.get(event) ?? [];
            handlers.push(handler);
            this.listeners.set(event, handlers);
            return { event, handler };
        }

        unsubscribe(): void {
            // subscriptions are torn down together with the instance in these tests
        }

        emit(event: string, payload?: unknown): void {
            for (const handler of this.listeners.get(event) ?? []) {
                handler(payload);
            }
        }
    }

    const instances: FakeScatterplot[] = [];
    const createScatterplotMock = vi.fn(() => {
        const instance = new FakeScatterplot();
        instances.push(instance);
        return instance;
    });
    return {
        instances,
        createScatterplotMock,
        getCloud: vi.fn(),
        getModuleCloud: vi.fn(),
        getCloudSuggestions: vi.fn().mockResolvedValue([]),
        getSuggestionTags: vi.fn().mockResolvedValue([]),
        getSamplePreview: vi.fn(),
        getModule: vi.fn(),
        getMorphStatus: vi.fn().mockResolvedValue({ available: true, service: null }),
        play: vi.fn(),
    };
});

vi.mock("regl-scatterplot", () => ({
    default: createScatterplotMock,
}));

vi.mock("../../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../../src/api/cloud");
    return { ...actual, getCloud, getModuleCloud, getCloudSuggestions, getSuggestionTags };
});

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSamplePreview };
});

vi.mock("../../../src/samples/useAudioPreview", async () => {
    const actual = await vi.importActual<typeof AudioPreview>("../../../src/samples/useAudioPreview");
    return { ...actual, useAudioPreview: () => ({ play, playingKey: null, failure: null }) };
});

vi.mock("../../../src/api/morph", async () => {
    const actual = await vi.importActual<typeof MorphApi>("../../../src/api/morph");
    return { ...actual, getMorphStatus };
});

vi.mock("../../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../../src/api/modules");
    return { ...actual, getModule };
});

const RIGHT_BUTTON = 2;

function latestInstance(): (typeof instances)[number] {
    const instance = instances[instances.length - 1];
    if (instance === undefined) {
        throw new Error("no FakeScatterplot instance was created");
    }
    return instance;
}

function latestCanvas(): HTMLCanvasElement {
    const canvas = document.querySelector<HTMLCanvasElement>("canvas.cloud-dots");
    if (canvas === null) {
        throw new Error("canvas not found");
    }
    return canvas;
}

function renderPanel(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<CloudPanel />} />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
                <Route path="/modules/:moduleHash" element={<p>module route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("CloudPanel", () => {
    it("shows a loading state before either tab's points arrive", () => {
        getCloud.mockReturnValue(new Promise(() => undefined));
        getModuleCloud.mockReturnValue(new Promise(() => undefined));

        renderPanel();

        expect(screen.getByText("Loading…")).toBeInTheDocument();
    });

    it("renders a canvas for the Samples tab once its points have loaded", async () => {
        getCloud.mockResolvedValue([{ sample_hash: "a".repeat(64), x: 0, y: 0, category: "uncategorized" }]);
        getModuleCloud.mockResolvedValue([]);

        renderPanel();

        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
    });

    it("shows an error notice when the active tab's request fails", async () => {
        getCloud.mockRejectedValue(new Error("service unavailable"));
        getModuleCloud.mockResolvedValue([]);

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("service unavailable");
        });
    });

    it("highlights the clicked sample in the shared selection store", async () => {
        const sampleHash = "b".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, category: "uncategorized" }]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });

        latestInstance().emit("select", { points: [0] });

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: sampleHash });
    });

    it("clears the shared highlight on a click that misses every point", async () => {
        const sampleHash = "f".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, category: "uncategorized" }]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        useSelectionStore.getState().highlightEntity({ kind: "sample", hash: sampleHash });

        fireEvent.click(latestCanvas());

        expect(useSelectionStore.getState().highlighted).toBeNull();
    });

    it("navigates to the double-clicked sample's route", async () => {
        const sampleHash = "c".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, category: "uncategorized" }]);
        getModuleCloud.mockResolvedValue([]);
        // The hover tooltip fetches a sample preview as soon as pointOver fires below.
        getSamplePreview.mockReturnValue(new Promise(() => undefined));
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        latestInstance().emit("pointOver", 0);

        fireEvent.dblClick(latestCanvas());

        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });

    it("switches to the Modules tab, showing its placeholder caption and points", async () => {
        getCloud.mockResolvedValue([]);
        const moduleHash = "d".repeat(64);
        getModuleCloud.mockResolvedValue([{ module_hash: moduleHash, x: 0, y: 0 }]);
        renderPanel();

        fireEvent.click(screen.getByRole("button", { name: "Modules" }));

        expect(screen.getByText(/spectral-distance embedding/)).toBeInTheDocument();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
    });

    it("navigates to the double-clicked module's route from the Modules tab", async () => {
        getCloud.mockResolvedValue([]);
        const moduleHash = "e".repeat(64);
        getModuleCloud.mockResolvedValue([{ module_hash: moduleHash, x: 0, y: 0 }]);
        // The hover tooltip fetches module detail as soon as pointOver fires below.
        getModule.mockReturnValue(new Promise(() => undefined));
        renderPanel();
        fireEvent.click(screen.getByRole("button", { name: "Modules" }));
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        latestInstance().emit("pointOver", 0);

        fireEvent.dblClick(latestCanvas());

        expect(await screen.findByText("module route")).toBeInTheDocument();
    });

    it("shows a hover tooltip with the sample's name and hash", async () => {
        const sampleHash = "1".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, category: "uncategorized" }]);
        getModuleCloud.mockResolvedValue([]);
        getSamplePreview.mockResolvedValue({
            display_name: "kick",
            category: "kick",
            suggested_label: null,
            hand_label: null,
            thumbnail: [],
        });
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });

        latestInstance().emit("pointOver", 0);

        expect(await screen.findByText("kick")).toBeInTheDocument();
        expect(screen.getByText(sampleHash.slice(0, 8))).toBeInTheDocument();
    });

    it("colors by the listening model's suggestions, with a legend of the tags it suggests first", async () => {
        const sampleHash = "3".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, category: "uncategorized" }]);
        getModuleCloud.mockResolvedValue([]);
        getCloudSuggestions.mockResolvedValue([{ sample_hash: sampleHash, path: ["BASS DRUM"], score: 0.8 }]);
        getSuggestionTags.mockResolvedValue([{ path: ["BASS DRUM"], sample_count: 1, rank: 0 }]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

        expect(await screen.findByRole("button", { name: /BASS DRUM/ })).toHaveAttribute("aria-pressed", "true");
        await waitFor(() => {
            expect(latestInstance().draw).toHaveBeenCalledWith([[expect.any(Number), expect.any(Number), 1]], {
                zDataType: "categorical",
            });
        });
    });

    it("hides the hover tooltip once the cursor leaves the point", async () => {
        const sampleHash = "2".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, category: "uncategorized" }]);
        getModuleCloud.mockResolvedValue([]);
        getSamplePreview.mockResolvedValue({
            display_name: "snare",
            category: "snare",
            suggested_label: null,
            hand_label: null,
            thumbnail: [],
        });
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        latestInstance().emit("pointOver", 0);
        await screen.findByText("snare");

        latestInstance().emit("pointOut");

        await waitFor(() => {
            expect(screen.queryByText("snare")).not.toBeInTheDocument();
        });
    });

    it("joins the highlighted sample and a right-clicked one into the morph pair", async () => {
        const anchor = "4".repeat(64);
        const other = "5".repeat(64);
        getCloud.mockResolvedValue([
            { sample_hash: anchor, x: 0, y: 0, category: "uncategorized", playback_rate_hz: 8363 },
            { sample_hash: other, x: 1, y: 1, category: "uncategorized", playback_rate_hz: 16726 },
        ]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        act(() => {
            useSelectionStore.getState().highlightEntity({ kind: "sample", hash: anchor });
        });
        latestInstance().emit("pointOver", 1);

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON });
        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(useMorphStore.getState()).toMatchObject({ first: anchor, second: other });
        expect(play).not.toHaveBeenCalled();
    });

    it("joins two samples dragged from one to the other with the right button", async () => {
        const first = "9".repeat(64);
        const second = "0".repeat(64);
        getCloud.mockResolvedValue([
            { sample_hash: first, x: 0, y: 0, category: "uncategorized", playback_rate_hz: 8363 },
            { sample_hash: second, x: 1, y: 1, category: "uncategorized", playback_rate_hz: 16726 },
        ]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        latestInstance().emit("pointOver", 0);

        fireEvent.mouseDown(latestCanvas(), { button: RIGHT_BUTTON });
        latestInstance().emit("pointOver", 1);
        fireEvent.mouseUp(latestCanvas(), { button: RIGHT_BUTTON });

        expect(useMorphStore.getState()).toMatchObject({ first, second });
        expect(useSelectionStore.getState().highlighted).toBeNull();
    });

    it("plays the morph as its file states when the marker is released", async () => {
        const first = "6".repeat(64);
        const second = "7".repeat(64);
        getCloud.mockResolvedValue([
            { sample_hash: first, x: 0, y: 0, category: "uncategorized", playback_rate_hz: 8363 },
            { sample_hash: second, x: 1, y: 1, category: "uncategorized", playback_rate_hz: 16726 },
        ]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        act(() => {
            useMorphStore.getState().join(first, second);
        });
        const marker = await screen.findByRole("slider", { name: "Morph weight" });

        fireEvent.pointerDown(marker, { pointerId: 1, clientX: 10, clientY: 20 });
        fireEvent.pointerUp(marker, { pointerId: 1, clientX: 10, clientY: 20 });

        expect(play).toHaveBeenCalledWith({
            key: `/api/morph/audio?first=${first}&second=${second}&weight=0.5`,
            url: `/api/morph/audio?first=${first}&second=${second}&weight=0.5`,
            playbackRateHz: null,
        });
    });

    it("plays no morph on a marker release while no renderer answers", async () => {
        const first = "6".repeat(64);
        const second = "7".repeat(64);
        getMorphStatus.mockResolvedValue({ available: false, service: null });
        getCloud.mockResolvedValue([
            { sample_hash: first, x: 0, y: 0, category: "uncategorized", playback_rate_hz: 8363 },
            { sample_hash: second, x: 1, y: 1, category: "uncategorized", playback_rate_hz: 16726 },
        ]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(getMorphStatus).toHaveBeenCalled();
        });
        act(() => {
            useMorphStore.getState().join(first, second);
        });
        const marker = await screen.findByRole("slider", { name: "Morph weight" });

        fireEvent.pointerDown(marker, { pointerId: 1, clientX: 10, clientY: 20 });
        fireEvent.pointerUp(marker, { pointerId: 1, clientX: 10, clientY: 20 });

        expect(play).not.toHaveBeenCalled();
    });
    it("asks for the suggestions and their tags only once the Suggestions mode is chosen", async () => {
        const sampleHash = "8".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, category: "uncategorized" }]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });

        expect(getCloudSuggestions).not.toHaveBeenCalled();
        expect(getSuggestionTags).not.toHaveBeenCalled();

        fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

        await waitFor(() => {
            expect(getCloudSuggestions).toHaveBeenCalledTimes(1);
        });
        expect(getSuggestionTags).toHaveBeenCalledTimes(1);
    });
});
