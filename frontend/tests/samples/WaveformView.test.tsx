import { render } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import { NO_TRACES, type WaveformTrace, WaveformView } from "../../src/samples/WaveformView";

const PEAKS = [
    { minimum: -1, maximum: 1 },
    { minimum: -0.5, maximum: 0.5 },
];

const TRACES: readonly WaveformTrace[] = [
    { peaks: PEAKS, share: 1, color: "rgb(0 0 0 / 1)" },
    { peaks: PEAKS, share: 0.5, color: "rgb(255 255 255 / 1)" },
];

function renderView(traces: readonly WaveformTrace[], playheadFraction: number | null): HTMLElement {
    const { container } = render(
        <WaveformView
            containerRef={createRef<HTMLDivElement>()}
            isPlaying={false}
            traces={traces}
            playheadFraction={playheadFraction}
        />,
    );
    return container;
}

describe("WaveformView", () => {
    it("leaves the frame to the waveform alone when nothing is traced behind it", () => {
        const container = renderView(NO_TRACES, null);

        expect(container.querySelector(".wave-traces")).toBeNull();
        expect(container.querySelector(".wave-host")).toBeInTheDocument();
    });

    it("lays a canvas behind the waveform once there are contours to trace", () => {
        const container = renderView(TRACES, null);

        expect(container.querySelector(".wave-traces")).toBeInTheDocument();
    });

    it("stands the playhead at the share of the frame the sound has reached", () => {
        const container = renderView(TRACES, 0.25);

        expect(container.querySelector(".wave-playhead")).toHaveStyle({ left: "25%" });
    });

    it("shows no playhead for a waveform whose sound comes from its own transport", () => {
        const container = renderView(TRACES, null);

        expect(container.querySelector(".wave-playhead")).toBeNull();
    });
});
