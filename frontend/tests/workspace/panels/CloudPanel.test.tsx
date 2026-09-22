import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../../src/api/cloud";
import type * as CurationApi from "../../../src/api/curation";
import type * as ModulesApi from "../../../src/api/modules";
import type * as MorphApi from "../../../src/api/morph";
import type * as SamplesApi from "../../../src/api/samples";
import { COARSE_POINTER_MEDIA_QUERY } from "../../../src/layout/layoutMode";
import { useMorphStore } from "../../../src/morph/morphStore";
import type * as AudioPreview from "../../../src/samples/useAudioPreview";
import { LONG_PRESS_HOLD_MS } from "../../../src/shared/gestures/gestureThresholds";
import { CloudPanel } from "../../../src/workspace/panels/CloudPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";
import { stubMatchMedia } from "../../support/matchMedia";

const {
    instances,
    createScatterplotMock,
    getCloud,
    getModuleCloud,
    getCloudCategories,
    getCategoryTags,
    getCloudLabels,
    getLabelTags,
    getSamplePreview,
    getSample,
    getSampleRelations,
    getSimilarSamples,
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
        readonly hover = vi.fn();
        readonly redraw = vi.fn();
        readonly zoomToArea = vi.fn().mockResolvedValue(undefined);
        readonly camera = { pan: vi.fn(), scale: vi.fn() };
        readonly get = vi.fn((property: string) => {
            if (property === "cameraView") {
                return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
            }
            return property === "camera" ? this.camera : undefined;
        });
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
        getCloudCategories: vi.fn().mockResolvedValue([]),
        getCategoryTags: vi.fn().mockResolvedValue([]),
        getCloudLabels: vi.fn().mockResolvedValue([]),
        getLabelTags: vi.fn().mockResolvedValue([]),
        getSamplePreview: vi.fn(),
        getSample: vi.fn().mockRejectedValue(new Error("no catalog behind this test")),
        getSampleRelations: vi.fn().mockResolvedValue([]),
        getSimilarSamples: vi.fn().mockResolvedValue([]),
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
    return { ...actual, getCloud, getModuleCloud, getCloudCategories, getCategoryTags, getCloudLabels };
});

vi.mock("../../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../../src/api/curation");
    return { ...actual, getLabelTags };
});

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSamplePreview, getSample, getSampleRelations, getSimilarSamples };
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

/** What every test starts from: a renderer that answers, and a catalog that names any sample the strip offers. */
beforeEach(() => {
    getMorphStatus.mockResolvedValue({ available: true, service: null });
    getSamplePreview.mockResolvedValue({ display_name: "", category: null, hand_label: null, thumbnail: null });
});

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
        getCloud.mockResolvedValue([{ sample_hash: "a".repeat(64), x: 0, y: 0 }]);
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
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0 }]);
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
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0 }]);
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
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0 }]);
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
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0 }]);
        getModuleCloud.mockResolvedValue([]);
        getSamplePreview.mockResolvedValue({
            display_name: "kick",
            category: null,
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

    it("colors by category from the start, each sample by its first pick under a legend of the tags picked first", async () => {
        const sampleHash = "3".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0 }]);
        getModuleCloud.mockResolvedValue([]);
        getCloudCategories.mockResolvedValue([{ sample_hash: sampleHash, path: ["BASS DRUM"], score: 0.8 }]);
        getCategoryTags.mockResolvedValue([{ path: ["BASS DRUM"], sample_count: 1, rank: 0 }]);
        renderPanel();

        expect(screen.getByRole("button", { name: "Category" })).toHaveAttribute("aria-pressed", "true");
        expect(await screen.findByRole("button", { name: /BASS DRUM/ })).toHaveAttribute("aria-pressed", "true");
        await waitFor(() => {
            expect(latestInstance().draw).toHaveBeenCalledWith([[expect.any(Number), expect.any(Number), 1]], {
                zDataType: "categorical",
            });
        });
    });

    it("hides the hover tooltip once the cursor leaves the point", async () => {
        const sampleHash = "2".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0 }]);
        getModuleCloud.mockResolvedValue([]);
        getSamplePreview.mockResolvedValue({
            display_name: "snare",
            category: null,
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
            { sample_hash: anchor, x: 0, y: 0, playback_rate_hz: 8363 },
            { sample_hash: other, x: 1, y: 1, playback_rate_hz: 16726 },
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
            { sample_hash: first, x: 0, y: 0, playback_rate_hz: 8363 },
            { sample_hash: second, x: 1, y: 1, playback_rate_hz: 16726 },
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
            { sample_hash: first, x: 0, y: 0, playback_rate_hz: 8363 },
            { sample_hash: second, x: 1, y: 1, playback_rate_hz: 16726 },
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
        expect(useMorphStore.getState().renderedWeight).toBe(0.5);
    });

    it("plays no morph on a marker release while no renderer answers", async () => {
        const first = "6".repeat(64);
        const second = "7".repeat(64);
        getMorphStatus.mockResolvedValue({ available: false, service: null });
        getCloud.mockResolvedValue([
            { sample_hash: first, x: 0, y: 0, playback_rate_hz: 8363 },
            { sample_hash: second, x: 1, y: 1, playback_rate_hz: 16726 },
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

    it("carries the morph strip under the samples cloud alone", async () => {
        getCloud.mockResolvedValue([{ sample_hash: "8".repeat(64), x: 0, y: 0, playback_rate_hz: 8363 }]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });

        expect(screen.getByRole("region", { name: "Morph" })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Modules" }));

        expect(screen.queryByRole("region", { name: "Morph" })).not.toBeInTheDocument();
    });

    it("frames both ends of the pair with room around them on request", async () => {
        const first = "6".repeat(64);
        const second = "7".repeat(64);
        getCloud.mockResolvedValue([
            { sample_hash: first, x: 0, y: 0, playback_rate_hz: 8363 },
            { sample_hash: second, x: 1, y: 1, playback_rate_hz: 16726 },
        ]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        expect(screen.getByRole("button", { name: "Frame the pair" })).toBeDisabled();
        act(() => {
            useMorphStore.getState().join(first, second);
        });
        await screen.findByRole("slider", { name: "Morph weight" });

        fireEvent.click(screen.getByRole("button", { name: "Frame the pair" }));

        const [area] = latestInstance().zoomToArea.mock.calls[0] as [Record<string, number>];
        expect(area.x).toBeCloseTo(-1.5, 5);
        expect(area.y).toBeCloseTo(-1.5, 5);
        expect(area.width).toBeCloseTo(3, 5);
        expect(area.height).toBeCloseTo(3, 5);
    });

    it("asks for the hand labels and their tags only once the Labels mode is chosen", async () => {
        const sampleHash = "8".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0 }]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });

        expect(getCloudCategories).toHaveBeenCalledTimes(1);
        expect(getCloudLabels).not.toHaveBeenCalled();
        expect(getLabelTags).not.toHaveBeenCalled();

        fireEvent.click(screen.getByRole("button", { name: "Labels" }));

        await waitFor(() => {
            expect(getCloudLabels).toHaveBeenCalledTimes(1);
        });
        expect(getLabelTags).toHaveBeenCalledTimes(1);
    });
});

describe("CloudPanel on touch", () => {
    const FIRST_HASH = "7".repeat(64);
    const SECOND_HASH = "8".repeat(64);
    const FINGER = { pointerId: 1, pointerType: "touch" };

    afterEach(() => {
        vi.useRealTimers();
    });

    /** The panel with two samples drawn: at (0, 600) and (600, 0) of the 600px test surface. */
    async function renderedPanel(): Promise<void> {
        getCloud.mockResolvedValue([
            { sample_hash: FIRST_HASH, x: 0, y: 0, playback_rate_hz: 8363 },
            { sample_hash: SECOND_HASH, x: 1, y: 1, playback_rate_hz: 16726 },
        ]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas.cloud-dots")).toBeInTheDocument();
        });
        await act(async () => {
            await Promise.resolve();
        });
    }

    function tap(x: number, y: number): void {
        fireEvent.pointerDown(latestCanvas(), { ...FINGER, clientX: x, clientY: y });
        fireEvent.pointerUp(latestCanvas(), { ...FINGER, clientX: x, clientY: y });
    }

    it("pairs two tapped samples in Pair mode, then leaves the mode", async () => {
        await renderedPanel();

        fireEvent.click(screen.getByRole("button", { name: "Pair" }));
        expect(screen.getByRole("status")).toHaveTextContent("Pair: tap the first sample");

        tap(5, 595);
        expect(screen.getByRole("status")).toHaveTextContent("Now tap the second");
        expect(useSelectionStore.getState().highlighted).toBeNull();

        tap(595, 5);

        expect(useMorphStore.getState()).toMatchObject({ first: FIRST_HASH, second: SECOND_HASH });
        expect(screen.getByRole("button", { name: "Pair" })).toHaveAttribute("aria-pressed", "false");
        expect(screen.queryByText(/tap the first sample|Now tap the second/)).not.toBeInTheDocument();
    });

    it("shows a tap card for the point in hand under touch, playing it as the tap lands", async () => {
        stubMatchMedia(new Set([COARSE_POINTER_MEDIA_QUERY]));
        getSamplePreview.mockResolvedValue({ display_name: "kick", category: null, hand_label: null, thumbnail: null });
        await renderedPanel();

        tap(5, 595);

        await waitFor(() => {
            expect(screen.getByRole("region", { name: "Tapped point" })).toHaveTextContent("kick");
        });
        expect(screen.getByRole("group", { name: "Sample actions" })).toBeInTheDocument();
        expect(play).toHaveBeenCalledWith(expect.objectContaining({ key: FIRST_HASH, playbackRateHz: 8363 }));
    });

    it("opens a held point's menu, which opens the point", async () => {
        await renderedPanel();
        vi.useFakeTimers();

        fireEvent.pointerDown(latestCanvas(), { ...FINGER, clientX: 5, clientY: 595 });
        act(() => {
            vi.advanceTimersByTime(LONG_PRESS_HOLD_MS);
        });
        fireEvent.pointerUp(latestCanvas(), { ...FINGER, clientX: 5, clientY: 595 });
        vi.useRealTimers();

        const menu = screen.getByRole("dialog", { name: `Sample ${FIRST_HASH.slice(0, 8)}` });
        fireEvent.click(within(menu).getByRole("button", { name: "Open" }));

        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });

    it("moves the legend into a sheet in a narrow panel", async () => {
        vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
            x: 0,
            y: 0,
            width: 300,
            height: 600,
            top: 0,
            right: 300,
            bottom: 600,
            left: 0,
            toJSON: () => ({}),
        });
        getCloudCategories.mockResolvedValue([{ sample_hash: FIRST_HASH, path: ["BASS DRUM"], score: 0.8 }]);
        getCategoryTags.mockResolvedValue([{ path: ["BASS DRUM"], sample_count: 1, rank: 0 }]);
        await renderedPanel();

        fireEvent.click(await screen.findByRole("button", { name: "Legend" }));

        const sheet = screen.getByRole("dialog", { name: "Painted tags" });
        expect(screen.queryByRole("group", { name: "Painted tags", hidden: false })).toBe(
            within(sheet).getByRole("group", { name: "Painted tags" }),
        );
        fireEvent.click(within(sheet).getByRole("button", { name: /BASS DRUM/ }));
        expect(within(sheet).getByRole("button", { name: /BASS DRUM/ })).toHaveAttribute("aria-pressed", "false");
    });

    it("steps the zoom and centers on the point in hand from the tools", async () => {
        await renderedPanel();

        fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
        expect(latestInstance().camera.scale).toHaveBeenCalledWith([1.5, 1.5], [0, 0]);
        expect(screen.getByRole("button", { name: "Center on the selection" })).toBeDisabled();

        act(() => {
            useSelectionStore.getState().highlightEntity({ kind: "sample", hash: SECOND_HASH });
        });
        fireEvent.click(screen.getByRole("button", { name: "Center on the selection" }));

        expect(latestInstance().zoomToArea).toHaveBeenCalledTimes(1);
    });
});
