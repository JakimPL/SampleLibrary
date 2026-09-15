import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as MorphApi from "../../../src/api/morph";
import type * as SamplesApi from "../../../src/api/samples";
import { useMorphStore } from "../../../src/morph/morphStore";
import type * as AudioPreview from "../../../src/samples/useAudioPreview";
import { UNNAMED_SAMPLE_LABEL } from "../../../src/shared/labels";
import { MorphPanel } from "../../../src/workspace/panels/MorphPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const FIRST = "a".repeat(64);
const SECOND = "b".repeat(64);
const FIRST_RATE_HZ = 8363;
const SECOND_RATE_HZ = 16726;

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
    it("asks for a pair when none is joined, and shows it once a gesture joins two samples", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        useMorphStore.getState().clear();
        serveSamples();
        renderPanel();

        expect(screen.getByText(/No morph pair yet/)).toBeInTheDocument();

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

    it("moves the shared weight from the slider and plays the morph on release, as its file states", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();
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
            playbackRateHz: null,
        });
    });

    it("highlights an end on a click of its hash, staying on the panel", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();
        await screen.findByText("kick_808");

        fireEvent.click(screen.getByText(FIRST.slice(0, 8)));

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

        fireEvent.click(screen.getByRole("button", { name: "Clear" }));
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: null });
        expect(screen.getByText(/No morph pair yet/)).toBeInTheDocument();
    });

    it("says so while no inference process answers, and looks again on request", async () => {
        getMorphStatus.mockResolvedValue({ available: false, service: null });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();

        expect(await screen.findByRole("status")).toHaveTextContent("Morphing is offline");
        expect(screen.getByRole("button", { name: "▶ Play morph" })).toBeDisabled();

        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        fireEvent.click(screen.getByRole("button", { name: "Check again" }));

        await waitFor(() => {
            expect(screen.getByRole("button", { name: "▶ Play morph" })).toBeEnabled();
        });
        expect(getMorphStatus).toHaveBeenCalledTimes(2);
    });

    it("plays nothing when a key is let go with the weight where it was", async () => {
        getMorphStatus.mockResolvedValue({ available: true, service: SERVICE });
        serveSamples();
        useMorphStore.getState().join(FIRST, SECOND);
        renderPanel();
        await screen.findByText("kick_808");
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "▶ Play morph" })).toBeEnabled();
        });

        fireEvent.keyUp(screen.getByRole("slider", { name: "Morph weight" }), { key: "Tab" });

        expect(play).not.toHaveBeenCalled();
    });
});
