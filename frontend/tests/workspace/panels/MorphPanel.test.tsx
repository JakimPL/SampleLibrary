import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as MorphApi from "../../../src/api/morph";
import type * as SamplesApi from "../../../src/api/samples";
import { rateBetween } from "../../../src/morph/morphRate";
import { useMorphStore } from "../../../src/morph/morphStore";
import type * as AudioPreview from "../../../src/samples/useAudioPreview";
import { UNNAMED_SAMPLE_LABEL } from "../../../src/shared/labels";
import { MorphPanel } from "../../../src/workspace/panels/MorphPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const FIRST = "a".repeat(64);
const SECOND = "b".repeat(64);
const FIRST_RATE_HZ = 8363;
const SECOND_RATE_HZ = 16726;

const { getSample, getSampleRelations, getSimilarSamples, getMorphStatus, play } = vi.hoisted(() => ({
    getSample: vi.fn(),
    getSampleRelations: vi.fn().mockResolvedValue([]),
    getSimilarSamples: vi.fn().mockResolvedValue([]),
    getMorphStatus: vi.fn(),
    play: vi.fn(),
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples };
});

vi.mock("../../../src/api/morph", async () => {
    const actual = await vi.importActual<typeof MorphApi>("../../../src/api/morph");
    return { ...actual, getMorphStatus };
});

vi.mock("../../../src/samples/useAudioPreview", async () => {
    const actual = await vi.importActual<typeof AudioPreview>("../../../src/samples/useAudioPreview");
    return { ...actual, useAudioPreview: () => ({ play, playingKey: null }) };
});

const SERVICE = {
    model: "principal_components",
    codec: "principal_components",
    canonicalizer: "log_frequency",
    latent_size: 256,
    vocoder: "restored",
    restorer: "restorer",
    device: "cpu",
    fingerprint: "f".repeat(64),
    weight_steps: 16,
};

function serveSamples(): void {
    getSample.mockImplementation((hash: string) =>
        Promise.resolve(
            hash === FIRST
                ? { hash, display_name: "kick_808", playback_rate_hz: FIRST_RATE_HZ }
                : { hash, display_name: "", playback_rate_hz: SECOND_RATE_HZ },
        ),
    );
}

describe("MorphPanel", () => {
    it("asks for a pair when none is joined, and offers the selection once it holds two samples", () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        render(<MorphPanel />);

        expect(screen.getByText(/No morph pair yet/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Use selection" })).toBeDisabled();

        act(() => {
            useSelectionStore.getState().focusSample(FIRST);
            useSelectionStore.getState().setComparisonSample(SECOND);
        });
        serveSamples();
        fireEvent.click(screen.getByRole("button", { name: "Use selection" }));

        expect(useMorphStore.getState()).toMatchObject({ first: FIRST, second: SECOND });
    });

    it("names both ends and the rate the weight puts the morph at", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().setPair(FIRST, SECOND);
        render(<MorphPanel />);

        expect(await screen.findByText("kick_808")).toBeInTheDocument();
        expect(screen.getByText(UNNAMED_SAMPLE_LABEL)).toBeInTheDocument();
        const rateHz = Math.round(rateBetween(FIRST_RATE_HZ, SECOND_RATE_HZ, 0.5));
        expect(screen.getByText(`0.50 · ${String(rateHz)} Hz`)).toBeInTheDocument();
    });

    it("moves the shared weight from the slider and plays the morph on release", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().setPair(FIRST, SECOND);
        render(<MorphPanel />);
        await screen.findByText("kick_808");
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "▶ Play morph" })).toBeEnabled();
        });

        fireEvent.change(screen.getByRole("slider", { name: "Morph weight" }), { target: { value: "0.25" } });
        fireEvent.pointerUp(screen.getByRole("slider", { name: "Morph weight" }));

        expect(useMorphStore.getState().weight).toBe(0.25);
        expect(play).toHaveBeenCalledWith({
            key: `/api/morph/audio?first=${FIRST}&second=${SECOND}&weight=0.25`,
            url: `/api/morph/audio?first=${FIRST}&second=${SECOND}&weight=0.25`,
            playbackRateHz: rateBetween(FIRST_RATE_HZ, SECOND_RATE_HZ, 0.25),
        });
    });

    it("swaps the ends with the weight mirrored, and clears the pair", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().setPair(FIRST, SECOND);
        useMorphStore.getState().setWeight(0.25);
        render(<MorphPanel />);
        await screen.findByText("kick_808");

        fireEvent.click(screen.getByRole("button", { name: "Swap the two ends" }));
        expect(useMorphStore.getState()).toMatchObject({ first: SECOND, second: FIRST, weight: 0.75 });

        fireEvent.click(screen.getByRole("button", { name: "Clear" }));
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: null });
        expect(screen.getByText(/No morph pair yet/)).toBeInTheDocument();
    });

    it("says so while no inference process answers, and looks again on request", async () => {
        getMorphStatus.mockResolvedValue({ available: false, service: null });
        serveSamples();
        useMorphStore.getState().setPair(FIRST, SECOND);
        render(<MorphPanel />);

        expect(await screen.findByRole("status")).toHaveTextContent("Morphing is offline");
        expect(screen.getByRole("button", { name: "▶ Play morph" })).toBeDisabled();

        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        fireEvent.click(screen.getByRole("button", { name: "Check again" }));

        await waitFor(() => {
            expect(screen.getByRole("button", { name: "▶ Play morph" })).toBeEnabled();
        });
        expect(getMorphStatus).toHaveBeenCalledTimes(2);
    });
});
