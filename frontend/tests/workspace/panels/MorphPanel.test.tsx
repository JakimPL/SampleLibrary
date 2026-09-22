import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as MorphApi from "../../../src/api/morph";
import type * as SamplesApi from "../../../src/api/samples";
import { DEFAULT_WEIGHT, useMorphStore } from "../../../src/morph/morphStore";
import type * as AudioPreview from "../../../src/samples/useAudioPreview";
import { UNNAMED_SAMPLE_LABEL } from "../../../src/shared/labels";
import { MorphPanel } from "../../../src/workspace/panels/MorphPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const FIRST = "a".repeat(64);
const SECOND = "b".repeat(64);
const FIRST_RATE_HZ = 8363;
const SECOND_RATE_HZ = 16726;
const STORED_SECONDS = 0.5;
const MOVED_WEIGHT = 0.25;
const MOVED_RENDER_URL = `/api/morph/audio?first=${FIRST}&second=${SECOND}&weight=${String(MOVED_WEIGHT)}`;

const { getSample, getSampleRelations, getSimilarSamples, getSampleDistance, getMorphStatus, play } = vi.hoisted(
    () => ({
        getSample: vi.fn(),
        getSampleRelations: vi.fn().mockResolvedValue([]),
        getSimilarSamples: vi.fn().mockResolvedValue([]),
        getSampleDistance: vi.fn().mockReturnValue(new Promise(() => undefined)),
        getMorphStatus: vi.fn(),
        play: vi.fn(),
    }),
);

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples, getSampleDistance };
});

vi.mock("../../../src/api/morph", async () => {
    const actual = await vi.importActual<typeof MorphApi>("../../../src/api/morph");
    return { ...actual, getMorphStatus };
});

vi.mock("../../../src/samples/useAudioPreview", async () => {
    const actual = await vi.importActual<typeof AudioPreview>("../../../src/samples/useAudioPreview");
    return { ...actual, useAudioPreview: () => ({ play, playingKey: null, failure: null }) };
});

const SERVICE = {
    name: "envelope-first",
    fingerprint: "f".repeat(64),
    weight_steps: 16,
    description: {},
};

function renderPanel(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<MorphPanel />} />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

/** One letting go of the slider: what the process answers, whether the weight moved under the pointer, and whether the render sounds. */
interface ReleaseCase {
    readonly name: string;
    readonly available: boolean;
    readonly moved: boolean;
    readonly plays: boolean;
}

const RELEASE_CASES: readonly ReleaseCase[] = [
    { name: "plays the render at the weight it was left at", available: true, moved: true, plays: true },
    { name: "plays nothing when the weight was let go where it stood", available: true, moved: false, plays: false },
    { name: "plays nothing while no inference process answers", available: false, moved: true, plays: false },
];

/** What the waveform shows: whether a process answers, whether a weight has been let go, and whether a render stands drawn. */
interface WaveformCase {
    readonly name: string;
    readonly available: boolean;
    readonly released: boolean;
    readonly drawn: boolean;
    readonly hint: RegExp | null;
}

const WAVEFORM_CASES: readonly WaveformCase[] = [
    {
        name: "asks for a weight to be let go before it draws anything",
        available: true,
        released: false,
        drawn: false,
        hint: /Let the slider go/,
    },
    {
        name: "draws the render once a weight has been let go",
        available: true,
        released: true,
        drawn: true,
        hint: null,
    },
    {
        name: "says what it waits on while no inference process answers",
        available: false,
        released: true,
        drawn: false,
        hint: /once an inference process answers/,
    },
];

function serveSamples(): void {
    getSample.mockImplementation((hash: string) =>
        Promise.resolve(
            hash === FIRST
                ? {
                      hash,
                      display_name: "kick_808",
                      playback_rate_hz: FIRST_RATE_HZ,
                      duration_seconds: STORED_SECONDS,
                  }
                : { hash, display_name: "", playback_rate_hz: SECOND_RATE_HZ, duration_seconds: STORED_SECONDS },
        ),
    );
}

async function showPair(available: boolean): Promise<void> {
    getMorphStatus.mockResolvedValue(
        available ? { available: true, service: SERVICE } : { available: false, service: null },
    );
    serveSamples();
    useMorphStore.getState().join(FIRST, SECOND);
    renderPanel();
    await screen.findByText("kick_808");
    if (!available) {
        await screen.findByRole("status");
    }
}

function letTheSliderGo(weight: number): void {
    const slider = screen.getByRole("slider", { name: "Morph weight" });
    fireEvent.change(slider, { target: { value: String(weight) } });
    fireEvent.pointerUp(slider);
}

describe("MorphPanel", () => {
    it("asks for a pair when none is joined, and shows it once a gesture joins two samples", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        useMorphStore.getState().clear();
        serveSamples();
        renderPanel();

        expect(screen.queryByRole("slider", { name: "Morph weight" })).not.toBeInTheDocument();

        act(() => {
            useMorphStore.getState().join(FIRST, SECOND);
        });

        expect(await screen.findByText("kick_808")).toBeInTheDocument();
    });

    it("states how far apart the two ends of the pair sit", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        getSampleDistance.mockResolvedValue({ sample_hash: FIRST, other_hash: SECOND, distance: 25.2468 });
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();

        expect(await screen.findByText("distance 25.247")).toBeInTheDocument();
        expect(getSampleDistance).toHaveBeenCalledWith(FIRST, SECOND);
    });

    it("names both ends and states the weight", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();

        expect(await screen.findByText("kick_808")).toBeInTheDocument();
        expect(screen.getByText(UNNAMED_SAMPLE_LABEL)).toBeInTheDocument();
        expect(screen.getByText("0.50")).toBeInTheDocument();
    });

    it.each(RELEASE_CASES)("$name", async ({ available, moved, plays }: ReleaseCase) => {
        getMorphStatus.mockResolvedValue(
            available ? { available: true, service: SERVICE } : { available: false, service: null },
        );
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();
        await screen.findByText("kick_808");
        if (!available) {
            await screen.findByRole("status");
        }

        const slider = screen.getByRole("slider", { name: "Morph weight" });
        if (moved) {
            fireEvent.change(slider, { target: { value: String(MOVED_WEIGHT) } });
        }
        fireEvent.pointerUp(slider);

        expect(useMorphStore.getState().weight).toBe(moved ? MOVED_WEIGHT : DEFAULT_WEIGHT);
        expect(play).toHaveBeenCalledTimes(plays ? 1 : 0);
        if (plays) {
            expect(play).toHaveBeenCalledWith({
                key: MOVED_RENDER_URL,
                url: MOVED_RENDER_URL,
                playbackRateHz: null,
            });
        }
    });

    it.each(WAVEFORM_CASES)("$name", async ({ available, released, drawn, hint }: WaveformCase) => {
        await showPair(available);
        if (released) {
            letTheSliderGo(MOVED_WEIGHT);
        }

        expect(screen.getByRole("button", { name: "Play the morph" })).toHaveProperty("disabled", !drawn);
        expect(screen.queryByRole("link", { name: "Save this render" })).toStrictEqual(
            drawn ? expect.anything() : null,
        );
        if (hint === null) {
            expect(screen.queryByText(/Let the slider go|inference process answers/)).not.toBeInTheDocument();
        } else {
            expect(screen.getByText(hint)).toBeInTheDocument();
        }
    });

    it("sounds the point already drawn again, at the weight it was drawn for", async () => {
        await showPair(true);
        letTheSliderGo(MOVED_WEIGHT);
        play.mockClear();

        fireEvent.click(screen.getByRole("button", { name: "Play the morph" }));

        expect(play).toHaveBeenCalledWith({
            key: MOVED_RENDER_URL,
            url: MOVED_RENDER_URL,
            playbackRateHz: null,
        });
    });

    it("highlights an end on a click of its hash, staying on the panel", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();
        await screen.findByText("kick_808");

        fireEvent.click(screen.getByText(FIRST.slice(0, 8)), { detail: 1 });

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: FIRST });
        expect(screen.getByText("kick_808")).toBeInTheDocument();
    });

    it("opens an end in the sample detail on a double-click of its hash", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();
        await screen.findByText("kick_808");

        fireEvent.dblClick(screen.getByText(SECOND.slice(0, 8)));

        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });

    it("swaps the ends with the weight mirrored, and clears the pair", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        useMorphStore.getState().setWeight(0.25);
        renderPanel();
        await screen.findByText("kick_808");

        fireEvent.click(screen.getByRole("button", { name: "Swap the two ends" }));
        expect(useMorphStore.getState()).toMatchObject({ first: SECOND, second: FIRST, weight: 0.75 });

        fireEvent.click(screen.getByRole("button", { name: "Clear the pair" }));
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: null });
        expect(screen.queryByRole("slider", { name: "Morph weight" })).not.toBeInTheDocument();
    });

    it("says so while no inference process answers, and looks again on request", async () => {
        getMorphStatus.mockResolvedValue({ available: false, service: null });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();

        expect(await screen.findByRole("status")).toHaveTextContent("Morphing is offline");

        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        fireEvent.click(screen.getByRole("button", { name: "Check again" }));

        await waitFor(() => {
            expect(screen.queryByRole("status")).not.toBeInTheDocument();
        });
        expect(getMorphStatus).toHaveBeenCalledTimes(2);
    });

    it("plays nothing when a key is let go with the weight where it was", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();
        await screen.findByText("kick_808");

        fireEvent.keyUp(screen.getByRole("slider", { name: "Morph weight" }), { key: "Tab" });

        expect(play).not.toHaveBeenCalled();
    });
});
