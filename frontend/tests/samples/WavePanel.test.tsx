import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WavePanel } from "../../src/samples/WavePanel";

const READOUT = "0.00 s / 0.93 s";

function tagsOf(panel: Element | null): readonly string[] {
    return panel === null ? [] : [...panel.children].map((child) => child.tagName);
}

describe("WavePanel", () => {
    it("lays a row out: the play button, the frame with the time in its corner, the file to save", () => {
        const { container } = render(
            <WavePanel
                compact
                playButton={<button type="button">▶</button>}
                view={<p>the frame</p>}
                readout={READOUT}
                failure={null}
                controls={<span>a rate to choose</span>}
                download={
                    <a href="/a.wav" download="a.wav">
                        ⤓
                    </a>
                }
            />,
        );

        const panel = container.querySelector(".wave-panel");
        expect(panel).toHaveClass("wave-panel-compact");
        expect(tagsOf(panel)).toEqual(["BUTTON", "DIV", "A"]);
        expect(container.querySelector(".wave-panel-frame .wave-time")).toHaveTextContent(READOUT);
        expect(screen.queryByText("a rate to choose")).not.toBeInTheDocument();
    });

    it("keeps the row symmetric with a slot where there is no file, and the corner clear where the audio is missing", () => {
        const { container } = render(
            <WavePanel
                compact
                playButton={<button type="button">▶</button>}
                view={<p>the frame</p>}
                readout={READOUT}
                failure="the audio is gone"
                controls={null}
                download={null}
            />,
        );

        expect(tagsOf(container.querySelector(".wave-panel"))).toEqual(["BUTTON", "DIV", "SPAN"]);
        expect(container.querySelector(".wave-panel-slot")).toBeInTheDocument();
        expect(container.querySelector(".wave-time")).not.toBeInTheDocument();
        expect(screen.queryByText("the audio is gone")).not.toBeInTheDocument();
    });

    it("stands the frame over a transport row elsewhere, the controls and the file in the row", () => {
        const { container } = render(
            <WavePanel
                compact={false}
                playButton={<button type="button">▶</button>}
                view={<p>the frame</p>}
                readout={READOUT}
                failure={null}
                controls={<span>a rate to choose</span>}
                download={
                    <a href="/a.wav" download="a.wav">
                        ⤓
                    </a>
                }
            />,
        );

        const panel = container.querySelector(".wave-panel");
        expect(panel).not.toHaveClass("wave-panel-compact");
        expect(tagsOf(panel)).toEqual(["DIV", "DIV"]);
        expect(tagsOf(container.querySelector(".transport"))).toEqual(["BUTTON", "SPAN", "SPAN", "A"]);
        expect(container.querySelector(".transport .time")).toHaveTextContent(READOUT);
        expect(screen.getByText("a rate to choose")).toBeInTheDocument();
    });

    it("says in the transport row what is missing, in the time's place", () => {
        const { container } = render(
            <WavePanel
                compact={false}
                playButton={<button type="button">▶</button>}
                view={<p>the frame</p>}
                readout={READOUT}
                failure="the audio is gone"
                controls={null}
                download={null}
            />,
        );

        expect(screen.getByText("the audio is gone")).toBeInTheDocument();
        expect(container.querySelector(".time")).not.toBeInTheDocument();
    });
});
