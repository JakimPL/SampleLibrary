import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../../src/api/cloud";
import type * as SamplesApi from "../../../src/api/samples";
import { PHONE_MEDIA_QUERY } from "../../../src/layout/layoutMode";
import { routes } from "../../../src/navigation/router";
import { useSelectionStore } from "../../../src/workspace/selectionStore";
import { stubMatchMedia } from "../../support/matchMedia";

const { getSample, getSampleRelations, getSimilarSamples } = vi.hoisted(() => ({
    getSample: vi.fn(),
    getSampleRelations: vi.fn(),
    getSimilarSamples: vi.fn(),
}));

const { getCategoryTags } = vi.hoisted(() => ({ getCategoryTags: vi.fn().mockResolvedValue([]) }));

vi.mock("../../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../../src/api/cloud");
    return { ...actual, getCategoryTags };
});

vi.mock("wavesurfer.js", () => ({
    default: {
        create: () => ({
            on: () => () => undefined,
            play: vi.fn().mockResolvedValue(undefined),
            pause: vi.fn(),
            setTime: vi.fn(),
            setPlaybackRate: vi.fn(),
            setOptions: vi.fn(),
            destroy: vi.fn(),
        }),
    },
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples };
});

function renderShellAt(...entries: readonly string[]): ReturnType<typeof createMemoryRouter> {
    const router = createMemoryRouter(routes, { initialEntries: [...entries], initialIndex: entries.length - 1 });
    render(<RouterProvider router={router} />);
    return router;
}

/** The surface titled `title`, found by its label since a hidden region carries no accessible name. */
function surface(title: string): HTMLElement {
    const element = document.querySelector<HTMLElement>(`section.phone-surface[aria-label="${title}"]`);
    if (element === null) {
        throw new Error(`no surface is titled ${title}`);
    }
    return element;
}

describe("PhoneShell", () => {
    beforeEach(() => {
        stubMatchMedia(new Set([PHONE_MEDIA_QUERY]));
        getSample.mockResolvedValue({
            hash: "abc",
            depth: 16,
            channels: 1,
            frames: 4096,
            display_name: "kick",
            category: null,
            hand_label: null,
            rating: null,
            favorite: false,
            size_bytes: 8192,
            duration_seconds: 0.09,
            playback_rate_hz: 8363,
            playback_rates: [{ rate_hz: 8363, event_count: 2 }],
            categories: [],
            occurrences: [],
            files: [],
            equivalence_member_count: 1,
        });
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
    });

    it("opens on the samples tab, with the tab bar and the screen menu", () => {
        renderShellAt("/");

        expect(screen.getByRole("heading", { level: 1, name: "Samples" })).toBeInTheDocument();
        expect(screen.getByRole("navigation", { name: "Sections" })).toBeInTheDocument();
        expect(screen.getByText("More")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Samples" })).toHaveAttribute("aria-current", "page");
    });

    it("leaves the Cloud tab the whole height while nothing is in hand", async () => {
        renderShellAt("/cloud");

        expect(await screen.findByRole("heading", { level: 1, name: "Cloud" })).toBeInTheDocument();
        expect(document.querySelector(".phone-shell")).toHaveAttribute("data-tab", "cloud");
        expect(document.querySelector(".tray")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("link", { name: "Samples" }));
        await screen.findByRole("heading", { level: 1, name: "Samples" });

        expect(document.querySelector(".tray")).not.toBeInTheDocument();
    });

    it("keeps a tab mounted out of sight once it has been visited", async () => {
        renderShellAt("/");

        fireEvent.click(screen.getByRole("link", { name: "Modules" }));

        expect(await screen.findByRole("heading", { level: 1, name: "Modules" })).toBeInTheDocument();
        expect(surface("Samples")).toHaveAttribute("inert");
        expect(surface("Modules")).not.toHaveAttribute("inert");
    });

    it("opens a sample as a page over the tabs, focusing it and keeping the tray away", async () => {
        renderShellAt("/samples/abc");

        expect(await screen.findByRole("heading", { level: 1, name: "kick" })).toBeInTheDocument();
        expect(useSelectionStore.getState().focusedSampleHash).toBe("abc");
        expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
        expect(screen.queryByRole("region", { name: "Sample in hand" })).not.toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Samples" })).toHaveAttribute("aria-current", "page");
    });

    it("returns from a page opened cold to the samples tab, where the tray then names the sample", async () => {
        renderShellAt("/samples/abc");
        await screen.findByRole("heading", { level: 1, name: "kick" });

        fireEvent.click(screen.getByRole("button", { name: "Back" }));

        expect(await screen.findByRole("heading", { level: 1, name: "Samples" })).toBeInTheDocument();
        expect(await screen.findByRole("region", { name: "Sample in hand" })).toBeInTheDocument();
    });

    it("returns from a page to the tab it was opened from", async () => {
        const router = renderShellAt("/modules");
        await act(async () => {
            await router.navigate("/samples/abc");
        });
        await screen.findByRole("heading", { level: 1, name: "kick" });
        expect(screen.getByRole("link", { name: "Modules" })).toHaveAttribute("aria-current", "page");

        fireEvent.click(screen.getByRole("button", { name: "Back" }));

        await waitFor(() => {
            expect(router.state.location.pathname).toBe("/modules");
        });
    });

    it("opens the guide to the gestures from the screen menu", () => {
        renderShellAt("/");

        fireEvent.click(screen.getByText("More"));
        fireEvent.click(screen.getByRole("button", { name: "Keyboard and mouse" }));

        expect(screen.getByRole("dialog", { name: "Keyboard and mouse" })).toBeInTheDocument();
    });

    it("opens the diagnostics from the screen menu", () => {
        renderShellAt("/");

        fireEvent.click(screen.getByText("More"));
        fireEvent.click(screen.getByRole("button", { name: "Diagnostics" }));

        expect(screen.getByRole("dialog", { name: "Diagnostics" })).toBeInTheDocument();
    });

    it("shows a panel with no tab as a page from the screen menu", async () => {
        renderShellAt("/");

        fireEvent.click(screen.getByText("More"));
        fireEvent.click(screen.getByRole("link", { name: "Stats" }));

        expect(await screen.findByRole("heading", { level: 1, name: "Stats" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    });
});
