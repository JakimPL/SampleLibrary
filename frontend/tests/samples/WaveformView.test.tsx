import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import { NO_TRACES, type WaveformNotice, type WaveformTrace, WaveformView } from "../../src/samples/WaveformView";

const PEAKS = [
    { minimum: -1, maximum: 1 },
    { minimum: -0.5, maximum: 0.5 },
];

const TRACES: readonly WaveformTrace[] = [
    { peaks: PEAKS, share: 1, color: "rgb(0 0 0 / 1)", style: "outlined" },
    { peaks: PEAKS, share: 0.5, color: "rgb(255 255 255 / 1)", style: "filled" },
];

function renderView(
    traces: readonly WaveformTrace[],
    playheadFraction: number | null,
    notice: WaveformNotice | null = null,
): HTMLElement {
    const { container } = render(
        <WaveformView
            containerRef={createRef<HTMLDivElement>()}
            isPlaying={false}
            traces={traces}
            playheadFraction={playheadFraction}
            notice={notice}
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

    it("says in the frame itself why a contour is missing", () => {
        renderView(TRACES, null, { text: "the two ends are heard 9.2 times apart in rate", failed: true });

        expect(screen.getByRole("status")).toHaveTextContent("9.2 times apart in rate");
    });

    it("states what is waited on without announcing it as a failure", () => {
        renderView(TRACES, null, { text: "Let the slider go", failed: false });

        expect(screen.getByText("Let the slider go")).toBeInTheDocument();
        expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("shows no playhead for a waveform whose sound comes from its own transport", () => {
        const container = renderView(TRACES, null);

        expect(container.querySelector(".wave-playhead")).toBeNull();
    });
});
