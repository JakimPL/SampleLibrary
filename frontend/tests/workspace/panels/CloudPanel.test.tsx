import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../../src/api/cloud";
import type * as ModulesApi from "../../../src/api/modules";
import type * as SamplesApi from "../../../src/api/samples";
import { CloudPanel } from "../../../src/workspace/panels/CloudPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { instances, createScatterplotMock, getCloud, getModuleCloud, getSample, getSampleWaveform, getModule } =
    vi.hoisted(() => {
        class FakeScatterplot {
            readonly draw = vi.fn().mockResolvedValue(undefined);
            readonly select = vi.fn();
            readonly deselect = vi.fn();
            readonly destroy = vi.fn();
            readonly set = vi.fn().mockResolvedValue(undefined);
            readonly getScreenPosition = vi.fn((index: number) => [10 + index, 20 + index] as [number, number]);
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
            getSample: vi.fn(),
            getSampleWaveform: vi.fn(),
            getModule: vi.fn(),
        };
    });

vi.mock("regl-scatterplot", () => ({
    default: createScatterplotMock,
}));

vi.mock("../../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../../src/api/cloud");
    return { ...actual, getCloud, getModuleCloud };
});

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleWaveform };
});

vi.mock("../../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../../src/api/modules");
    return { ...actual, getModule };
});

function latestInstance(): (typeof instances)[number] {
    const instance = instances[instances.length - 1];
    if (instance === undefined) {
        throw new Error("no FakeScatterplot instance was created");
    }
    return instance;
}

function latestCanvas(): HTMLCanvasElement {
    const canvas = document.querySelector("canvas");
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
        getCloud.mockResolvedValue([{ sample_hash: "a".repeat(64), x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]);
        getModuleCloud.mockResolvedValue([]);

        renderPanel();

        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
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
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });

        latestInstance().emit("select", { points: [0] });

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: sampleHash });
    });

    it("clears the shared highlight on a click that misses every point", async () => {
        const sampleHash = "f".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]);
        getModuleCloud.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });
        useSelectionStore.getState().highlightEntity({ kind: "sample", hash: sampleHash });

        fireEvent.click(latestCanvas());

        expect(useSelectionStore.getState().highlighted).toBeNull();
    });

    it("navigates to the double-clicked sample's route", async () => {
        const sampleHash = "c".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]);
        getModuleCloud.mockResolvedValue([]);
        // The hover tooltip fetches a sample preview as soon as pointOver fires below.
        getSample.mockReturnValue(new Promise(() => undefined));
        getSampleWaveform.mockReturnValue(new Promise(() => undefined));
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });
        latestInstance().emit("pointOver", 0);

        fireEvent.dblClick(latestCanvas());

        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });

    it("switches to the Modules tab, showing its placeholder caption and points", async () => {
        getCloud.mockResolvedValue([]);
        const moduleHash = "d".repeat(64);
        getModuleCloud.mockResolvedValue([
            { module_hash: moduleHash, x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" },
        ]);
        renderPanel();

        fireEvent.click(screen.getByRole("button", { name: "Modules" }));

        expect(screen.getByText(/spectral-distance embedding/)).toBeInTheDocument();
        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });
    });

    it("navigates to the double-clicked module's route from the Modules tab", async () => {
        getCloud.mockResolvedValue([]);
        const moduleHash = "e".repeat(64);
        getModuleCloud.mockResolvedValue([
            { module_hash: moduleHash, x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" },
        ]);
        // The hover tooltip fetches module detail as soon as pointOver fires below.
        getModule.mockReturnValue(new Promise(() => undefined));
        renderPanel();
        fireEvent.click(screen.getByRole("button", { name: "Modules" }));
        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });
        latestInstance().emit("pointOver", 0);

        fireEvent.dblClick(latestCanvas());

        expect(await screen.findByText("module route")).toBeInTheDocument();
    });

    it("shows a hover tooltip with the sample's name and hash", async () => {
        const sampleHash = "1".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]);
        getModuleCloud.mockResolvedValue([]);
        getSample.mockResolvedValue({
            hash: sampleHash,
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [],
            size_bytes: 8192,
            display_name: "kick",
            dominant_rate_hz: 8363,
            duration_seconds: 0.09,
        });
        getSampleWaveform.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });

        latestInstance().emit("pointOver", 0);

        expect(await screen.findByText("kick")).toBeInTheDocument();
        expect(screen.getByText(sampleHash.slice(0, 8))).toBeInTheDocument();
    });

    it("hides the hover tooltip once the cursor leaves the point", async () => {
        const sampleHash = "2".repeat(64);
        getCloud.mockResolvedValue([{ sample_hash: sampleHash, x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]);
        getModuleCloud.mockResolvedValue([]);
        getSample.mockResolvedValue({
            hash: sampleHash,
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [],
            size_bytes: 8192,
            display_name: "snare",
            dominant_rate_hz: 8363,
            duration_seconds: 0.09,
        });
        getSampleWaveform.mockResolvedValue([]);
        renderPanel();
        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });
        latestInstance().emit("pointOver", 0);
        await screen.findByText("snare");

        latestInstance().emit("pointOut");

        await waitFor(() => {
            expect(screen.queryByText("snare")).not.toBeInTheDocument();
        });
    });
});
