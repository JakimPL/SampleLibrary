import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../../src/api/samples";
import { morphPreview } from "../../../src/morph/morphPreview";
import { useMorphStore } from "../../../src/morph/morphStore";
import { useAudioPreview } from "../../../src/samples/useAudioPreview";
import { PlayerStrip } from "../../../src/shell/player/PlayerStrip";
import { usePlayerStripStore } from "../../../src/shell/player/playerStripStore";
import { SampleDetailPanel } from "../../../src/workspace/panels/SampleDetailPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { instances, createMock, getSample, getSampleRelations, getSimilarSamples } = vi.hoisted(() => {
    class FakeWaveSurfer {
        private readonly listeners = new Map<string, ((...args: unknown[]) => void)[]>();
        readonly play = vi.fn().mockResolvedValue(undefined);
        readonly pause = vi.fn();
        readonly setTime = vi.fn();
        readonly setPlaybackRate = vi.fn();
        readonly setOptions = vi.fn();
        readonly destroy = vi.fn();

        on(event: string, callback: (...args: unknown[]) => void): () => void {
            const callbacks = this.listeners.get(event) ?? [];
            callbacks.push(callback);
            this.listeners.set(event, callbacks);
            return () => undefined;
        }

        emit(event: string, ...args: unknown[]): void {
            for (const callback of this.listeners.get(event) ?? []) {
                callback(...args);
            }
        }
    }
    const instances: FakeWaveSurfer[] = [];
    const createMock = vi.fn(() => {
        const instance = new FakeWaveSurfer();
        instances.push(instance);
        return instance;
    });
    return { instances, createMock, getSample: vi.fn(), getSampleRelations: vi.fn(), getSimilarSamples: vi.fn() };
});

vi.mock("wavesurfer.js", () => ({
    default: { create: createMock },
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples };
});

function latestInstance(): (typeof instances)[number] {
    const instance = instances[instances.length - 1];
    if (instance === undefined) {
        throw new Error("no FakeWaveSurfer instance was created");
    }
    return instance;
}

interface PlaybackRateFixture {
    readonly rate_hz: number;
    readonly event_count: number;
}

interface SampleDetailOverrides {
    readonly hash?: string;
    readonly playbackRateHz: number | null;
    readonly playbackRates?: readonly PlaybackRateFixture[];
}

function buildSampleDetail(overrides: SampleDetailOverrides): unknown {
    return {
        hash: overrides.hash ?? "abc",
        depth: 16,
        channels: 1,
        frames: 4096,
        display_name: "kick",
        size_bytes: 8192,
        duration_seconds: 0.09,
        playback_rate_hz: overrides.playbackRateHz,
        playback_rates: overrides.playbackRates ?? [],
        categories: [],
        occurrences: [],
        files: [],
    };
}

function catalogAnswers(detail: unknown): void {
    getSample.mockResolvedValue(detail);
    getSampleRelations.mockResolvedValue([]);
    getSimilarSamples.mockResolvedValue([]);
}

function renderStrip(onRevealMorph = vi.fn()): void {
    render(
        <MemoryRouter>
            <PlayerStrip onRevealMorph={onRevealMorph} />
        </MemoryRouter>,
    );
}

describe("PlayerStrip", () => {
    it("stays out of the way while no sample is focused and no morph sounds", () => {
        const { container } = render(<PlayerStrip onRevealMorph={vi.fn()} />);

        expect(getSample).not.toHaveBeenCalled();
        expect(container).toBeEmptyDOMElement();
    });

    it("plays the focused sample at the rate the library really sounds it at", async () => {
        catalogAnswers(
            buildSampleDetail({
                playbackRateHz: 22050,
                playbackRates: [
                    { rate_hz: 22050, event_count: 40 },
                    { rate_hz: 8363, event_count: 2 },
                ],
            }),
        );
        useSelectionStore.getState().focusSample("abc");

        renderStrip();

        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });
        await waitFor(() => {
            expect(createMock).toHaveBeenCalled();
        });
        act(() => {
            latestInstance().emit("ready", 1.0);
        });

        await waitFor(() => {
            expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(22050 / 44100, false);
        });
    });

    it("lets the person hear another rate the library plays the sample at", async () => {
        catalogAnswers(
            buildSampleDetail({
                playbackRateHz: 22050,
                playbackRates: [
                    { rate_hz: 22050, event_count: 40 },
                    { rate_hz: 8363, event_count: 2 },
                ],
            }),
        );
        useSelectionStore.getState().focusSample("abc");
        renderStrip();
        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: "8363" } });

        await waitFor(() => {
            expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(8363 / 44100, false);
        });
    });

    it("says so for a sample the catalog knows no rate for", async () => {
        catalogAnswers(buildSampleDetail({ playbackRateHz: null }));
        useSelectionStore.getState().focusSample("abc");

        renderStrip();

        expect(await screen.findByText(/no rate the library is known to play it at/)).toBeInTheDocument();
    });

    it("shares one request with the Sample Detail panel for the same focused sample", async () => {
        catalogAnswers(buildSampleDetail({ playbackRateHz: 8363, playbackRates: [{ rate_hz: 8363, event_count: 2 }] }));
        useSelectionStore.getState().focusSample("abc");

        render(
            <MemoryRouter>
                <SampleDetailPanel />
                <PlayerStrip onRevealMorph={vi.fn()} />
            </MemoryRouter>,
        );

        await waitFor(() => {
            expect(screen.getByRole("region", { name: "Player" })).toBeInTheDocument();
        });
        expect(getSample).toHaveBeenCalledTimes(1);
    });

    it("folds the waveform away and out again from its own toggle", async () => {
        catalogAnswers(buildSampleDetail({ playbackRateHz: 8363 }));
        useSelectionStore.getState().focusSample("abc");
        renderStrip();
        const strip = await screen.findByRole("region", { name: "Player" });
        expect(strip).toHaveClass("player-strip-expanded");

        fireEvent.click(screen.getByRole("button", { name: "Collapse the player" }));

        expect(strip).not.toHaveClass("player-strip-expanded");
        expect(usePlayerStripStore.getState().expanded).toBe(false);
        fireEvent.click(screen.getByRole("button", { name: "Expand the player" }));
        expect(strip).toHaveClass("player-strip-expanded");
    });

    it("leaves the page once the View menu takes it away", () => {
        useSelectionStore.getState().focusSample("abc");
        act(() => {
            usePlayerStripStore.getState().setVisible(false);
        });

        const { container } = render(<PlayerStrip onRevealMorph={vi.fn()} />);

        expect(container).toBeEmptyDOMElement();
        act(() => {
            usePlayerStripStore.getState().setVisible(true);
        });
    });

    it("names the morph that sounds and offers the panel that drew it", async () => {
        catalogAnswers(buildSampleDetail({ hash: "aaa", playbackRateHz: 8363 }));
        const onRevealMorph = vi.fn();
        act(() => {
            useMorphStore.getState().join("aaa", "bbb");
        });
        renderStrip(onRevealMorph);
        const { result } = renderHookPreview();

        act(() => {
            result.current.play(morphPreview("aaa", "bbb", useMorphStore.getState().weight));
        });

        const readout = await screen.findByRole("status");
        expect(readout).toHaveTextContent("Morph");
        expect(readout).toHaveTextContent("0.50");
        fireEvent.click(screen.getByRole("button", { name: "Show" }));
        expect(onRevealMorph).toHaveBeenCalled();
    });
});

function renderHookPreview(): { readonly result: { readonly current: ReturnType<typeof useAudioPreview> } } {
    let current: ReturnType<typeof useAudioPreview> | null = null;
    function Probe(): null {
        current = useAudioPreview();
        return null;
    }
    render(<Probe />);
    return {
        result: {
            get current(): ReturnType<typeof useAudioPreview> {
                if (current === null) {
                    throw new Error("the probe has not rendered");
                }
                return current;
            },
        },
    };
}
