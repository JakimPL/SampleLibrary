import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as MorphApi from "../../src/api/morph";
import type * as SamplesApi from "../../src/api/samples";
import { PHONE_MEDIA_QUERY } from "../../src/layout/layoutMode";
import { DEFAULT_WEIGHT, useMorphStore } from "../../src/morph/morphStore";
import { MorphStrip } from "../../src/morph/MorphStrip";
import { useMorphStripStore } from "../../src/morph/morphStripStore";
import type * as AudioPreview from "../../src/samples/useAudioPreview";
import { UNNAMED_SAMPLE_LABEL } from "../../src/shared/labels";
import { useSelectionStore } from "../../src/workspace/selectionStore";
import { stubMatchMedia } from "../support/matchMedia";

const FIRST = "a".repeat(64);
const SECOND = "b".repeat(64);
const FIRST_RATE_HZ = 8363;
const SECOND_RATE_HZ = 16726;
const STORED_SECONDS = 0.5;
const MOVED_WEIGHT = 0.25;
const MOVED_RENDER_URL = `/api/morph/audio?first=${FIRST}&second=${SECOND}&weight=${String(MOVED_WEIGHT)}`;
const NAMES: Readonly<Record<string, string>> = { [FIRST]: "kick_808", [SECOND]: "" };

const { getSample, getSamplePreview, getSampleRelations, getSimilarSamples, getSampleDistance, getMorphStatus, play } =
    vi.hoisted(() => ({
        getSample: vi.fn(),
        getSamplePreview: vi.fn(),
        getSampleRelations: vi.fn().mockResolvedValue([]),
        getSimilarSamples: vi.fn().mockResolvedValue([]),
        getSampleDistance: vi.fn().mockReturnValue(new Promise(() => undefined)),
        getMorphStatus: vi.fn(),
        play: vi.fn(),
    }));

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, getSample, getSamplePreview, getSampleRelations, getSimilarSamples, getSampleDistance };
});

vi.mock("../../src/api/morph", async () => {
    const actual = await vi.importActual<typeof MorphApi>("../../src/api/morph");
    return { ...actual, getMorphStatus };
});

vi.mock("../../src/samples/useAudioPreview", async () => {
    const actual = await vi.importActual<typeof AudioPreview>("../../src/samples/useAudioPreview");
    return { ...actual, useAudioPreview: () => ({ play, playingKey: null, failure: null }) };
});

const SERVICE = {
    name: "envelope-first",
    fingerprint: "f".repeat(64),
    weight_steps: 16,
    description: {},
};

function serveSamples(): void {
    getSample.mockImplementation((hash: string) =>
        Promise.resolve({
            hash,
            display_name: NAMES[hash] ?? "",
            playback_rate_hz: hash === FIRST ? FIRST_RATE_HZ : SECOND_RATE_HZ,
            duration_seconds: STORED_SECONDS,
        }),
    );
    getSamplePreview.mockImplementation((hash: string) =>
        Promise.resolve({ hash, display_name: NAMES[hash] ?? "", thumbnail: null, category: null, hand_label: null }),
    );
}

function serveMorph(available: boolean): void {
    getMorphStatus.mockResolvedValue(
        available ? { available: true, service: SERVICE } : { available: false, service: null },
    );
}

/** The strip with nothing chosen, a renderer answering. */
function showEmpty(): ReturnType<typeof render> {
    serveMorph(true);
    serveSamples();
    return render(<MorphStrip />);
}

/** The strip with a whole pair on it, the ends named, and its body open by itself. */
async function showPair(available: boolean): Promise<ReturnType<typeof render>> {
    serveMorph(available);
    serveSamples();
    useMorphStore.getState().join(FIRST, SECOND);
    const result = render(<MorphStrip />);
    await screen.findByText("kick_808");
    if (!available) {
        await screen.findByRole("status");
    }
    return result;
}

/** Lets the ends' details land, which a slot's play reads its rate from. */
async function settleDetails(): Promise<void> {
    await waitFor(() => {
        expect(getSample).toHaveBeenCalledWith(SECOND);
    });
    await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
    });
}

function slot(letter: "A" | "B"): HTMLElement {
    return screen.getByRole("button", { name: new RegExp(`^${letter}: `) });
}

function letTheSliderGo(weight: number): void {
    const slider = screen.getByRole("slider", { name: "Point along the morph" });
    fireEvent.change(slider, { target: { value: String(weight) } });
    fireEvent.pointerUp(slider);
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

describe("MorphStrip while the pair is open", () => {
    it("asks for a sample in each slot, with the swap and the waveform button at rest", () => {
        showEmpty();

        expect(screen.getByRole("button", { name: "A: click, then a sample" })).toHaveAttribute(
            "aria-pressed",
            "false",
        );
        expect(screen.getByRole("button", { name: "B: click, then a sample" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Swap the two ends" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Morph waveform" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Morph waveform" })).toHaveAttribute("aria-expanded", "false");
    });

    it("selects a slot on a click, which then waits for a sample, and lets go on the next click", () => {
        showEmpty();

        fireEvent.click(slot("A"));
        expect(screen.getByRole("button", { name: "A: now click a sample" })).toHaveAttribute("aria-pressed", "true");
        expect(useMorphStore.getState().selectedEnd).toBe("first");

        fireEvent.click(slot("A"));
        expect(screen.getByRole("button", { name: "A: click, then a sample" })).toHaveAttribute(
            "aria-pressed",
            "false",
        );
        expect(useMorphStore.getState().selectedEnd).toBeNull();
    });

    it("moves the selection from one slot to the other", () => {
        showEmpty();

        fireEvent.click(slot("A"));
        fireEvent.click(slot("B"));

        expect(useMorphStore.getState().selectedEnd).toBe("second");
        expect(slot("A")).toHaveAttribute("aria-pressed", "false");
        expect(slot("B")).toHaveAttribute("aria-pressed", "true");
    });

    it("shows the sample the selected end took, still waiting for the next", async () => {
        showEmpty();
        fireEvent.click(slot("A"));

        act(() => {
            useMorphStore.getState().takeSample(FIRST);
        });

        expect(await screen.findByRole("button", { name: "A: kick_808" })).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByRole("button", { name: "Clear A" })).toBeInTheDocument();
    });
});

describe("MorphStrip with a whole pair", () => {
    it("names both ends and opens the slider by itself", async () => {
        await showPair(true);

        expect(screen.getByText(UNNAMED_SAMPLE_LABEL)).toBeInTheDocument();
        expect(screen.getByRole("slider", { name: "Point along the morph" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Morph waveform" })).toHaveAttribute("aria-expanded", "true");
        expect(screen.getByRole("button", { name: "Swap the two ends" })).toBeEnabled();
    });

    it("plays a chosen end at its own rate, takes it in hand and selects its slot on a click", async () => {
        await showPair(true);
        await settleDetails();

        fireEvent.click(slot("A"));

        expect(play).toHaveBeenCalledWith(expect.objectContaining({ key: FIRST, playbackRateHz: FIRST_RATE_HZ }));
        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: FIRST });
        expect(useMorphStore.getState().selectedEnd).toBe("first");
    });

    it("lets an end go from its ×, closing the body with it", async () => {
        await showPair(true);

        fireEvent.click(screen.getByRole("button", { name: "Clear B" }));

        expect(useMorphStore.getState()).toMatchObject({ first: FIRST, second: null });
        expect(screen.queryByRole("slider", { name: "Point along the morph" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Morph waveform" })).toBeDisabled();
    });

    it("swaps the ends with the weight mirrored", async () => {
        await showPair(true);
        act(() => {
            useMorphStore.getState().setWeight(0.25);
        });

        fireEvent.click(screen.getByRole("button", { name: "Swap the two ends" }));

        expect(useMorphStore.getState()).toMatchObject({ first: SECOND, second: FIRST, weight: 0.75 });
    });

    it("hides and shows its body from the waveform button, and shows it on request from outside", async () => {
        await showPair(true);

        fireEvent.click(screen.getByRole("button", { name: "Morph waveform" }));
        expect(screen.queryByRole("slider", { name: "Point along the morph" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Morph waveform" })).toHaveAttribute("aria-expanded", "false");

        fireEvent.click(screen.getByRole("button", { name: "Morph waveform" }));
        expect(screen.getByRole("slider", { name: "Point along the morph" })).toBeInTheDocument();

        act(() => {
            useMorphStripStore.getState().setExpanded(false);
        });
        expect(screen.queryByRole("slider", { name: "Point along the morph" })).not.toBeInTheDocument();
        act(() => {
            useMorphStripStore.getState().setExpanded(true);
        });
        expect(screen.getByRole("slider", { name: "Point along the morph" })).toBeInTheDocument();
    });

    it("states how far apart the two ends of the pair sit, in the workspace", async () => {
        getSampleDistance.mockResolvedValue({ sample_hash: FIRST, other_hash: SECOND, distance: 25.2468 });
        await showPair(true);

        expect(await screen.findByText("distance 25.247")).toBeInTheDocument();
        expect(getSampleDistance).toHaveBeenCalledWith(FIRST, SECOND);
    });

    it("leaves the distance out on a phone", async () => {
        stubMatchMedia(new Set([PHONE_MEDIA_QUERY]));
        getSampleDistance.mockClear();
        await showPair(true);

        expect(screen.getByRole("slider", { name: "Point along the morph" })).toBeInTheDocument();
        expect(screen.queryByText(/distance/)).not.toBeInTheDocument();
        expect(getSampleDistance).not.toHaveBeenCalled();
    });

    it("lets the selection go as it leaves", async () => {
        const { unmount } = await showPair(true);
        fireEvent.click(slot("B"));
        expect(useMorphStore.getState().selectedEnd).toBe("second");

        unmount();

        expect(useMorphStore.getState().selectedEnd).toBeNull();
    });

    it("says so while no inference process answers, and looks again on request", async () => {
        await showPair(false);
        expect(screen.getByRole("status")).toHaveTextContent("Morphing is offline");

        serveMorph(true);
        fireEvent.click(screen.getByRole("button", { name: "Check again" }));

        await waitFor(() => {
            expect(screen.queryByRole("status")).not.toBeInTheDocument();
        });
        expect(getMorphStatus).toHaveBeenCalledTimes(2);
    });
});

describe("MorphStrip opened out", () => {
    it.each(RELEASE_CASES)("$name", async ({ available, moved, plays }: ReleaseCase) => {
        await showPair(available);

        const slider = screen.getByRole("slider", { name: "Point along the morph" });
        if (moved) {
            fireEvent.change(slider, { target: { value: String(MOVED_WEIGHT) } });
        }
        fireEvent.pointerUp(slider);

        expect(useMorphStore.getState().weight).toBe(moved ? MOVED_WEIGHT : DEFAULT_WEIGHT);
        expect(play).toHaveBeenCalledTimes(plays ? 1 : 0);
        if (plays) {
            expect(play).toHaveBeenCalledWith({ key: MOVED_RENDER_URL, url: MOVED_RENDER_URL, playbackRateHz: null });
            expect(useMorphStore.getState().renderedWeight).toBe(MOVED_WEIGHT);
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

    it("draws the point the marker on the cloud let go at", async () => {
        await showPair(true);

        act(() => {
            useMorphStore.getState().setWeight(MOVED_WEIGHT);
            useMorphStore.getState().markRendered();
        });

        expect(screen.getByRole("button", { name: "Play the morph" })).toBeEnabled();
        expect(screen.getByRole("link", { name: "Save this render" })).toHaveAttribute("href", MOVED_RENDER_URL);
    });

    it("sounds the point already drawn again, at the weight it was drawn for", async () => {
        await showPair(true);
        letTheSliderGo(MOVED_WEIGHT);
        play.mockClear();

        fireEvent.click(screen.getByRole("button", { name: "Play the morph" }));

        expect(play).toHaveBeenCalledWith({ key: MOVED_RENDER_URL, url: MOVED_RENDER_URL, playbackRateHz: null });
    });

    it("plays nothing when a key is let go with the weight where it was", async () => {
        await showPair(true);

        fireEvent.keyUp(screen.getByRole("slider", { name: "Point along the morph" }), { key: "Tab" });

        expect(play).not.toHaveBeenCalled();
    });
});
