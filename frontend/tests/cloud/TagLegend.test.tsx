import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { TopLevelTag } from "../../src/cloud/labelColoring";
import { TagLegend } from "../../src/cloud/TagLegend";

const EMPTY_CAPTION = "No sample carries a tag yet.";

const TAGS: readonly TopLevelTag[] = [
    { name: "LO-FI", sampleCount: 33, rank: 4 },
    { name: "SNARE", sampleCount: 21, rank: 0 },
    { name: "PIANO", sampleCount: 12, rank: 2 },
];

describe("TagLegend", () => {
    it("lists the painted tags with their counts, and every tag once expanded", async () => {
        render(<TagLegend tags={TAGS} painted={["SNARE"]} onToggle={vi.fn()} emptyCaption={EMPTY_CAPTION} />);

        const snare = screen.getByRole("button", { name: /SNARE/ });
        expect(snare).toHaveAttribute("aria-pressed", "true");
        expect(snare).toHaveTextContent("21");
        expect(screen.queryByRole("button", { name: /LO-FI/ })).not.toBeInTheDocument();

        await userEvent.click(screen.getByRole("button", { name: "+2 more" }));

        const lofi = screen.getByRole("button", { name: /LO-FI/ });
        expect(lofi).toHaveAttribute("aria-pressed", "false");
        expect(lofi).toHaveTextContent("33");
        expect(screen.getByRole("button", { name: /PIANO/ })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Painted only" })).toHaveAttribute("aria-expanded", "true");
    });

    it("collapses back to the painted tags", async () => {
        render(<TagLegend tags={TAGS} painted={["SNARE"]} onToggle={vi.fn()} emptyCaption={EMPTY_CAPTION} />);
        await userEvent.click(screen.getByRole("button", { name: "+2 more" }));

        await userEvent.click(screen.getByRole("button", { name: "Painted only" }));

        expect(screen.queryByRole("button", { name: /LO-FI/ })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "+2 more" })).toHaveAttribute("aria-expanded", "false");
    });

    it("offers the toggle only while some tags are hidden", () => {
        render(
            <TagLegend
                tags={TAGS}
                painted={["LO-FI", "SNARE", "PIANO"]}
                onToggle={vi.fn()}
                emptyCaption={EMPTY_CAPTION}
            />,
        );

        expect(screen.queryByRole("button", { name: /more/ })).not.toBeInTheDocument();
        expect(screen.getAllByRole("button")).toHaveLength(TAGS.length);
    });

    it("reports the tag a person toggles, whether painted or revealed", async () => {
        const onToggle = vi.fn();
        render(<TagLegend tags={TAGS} painted={["SNARE"]} onToggle={onToggle} emptyCaption={EMPTY_CAPTION} />);

        await userEvent.click(screen.getByRole("button", { name: /SNARE/ }));
        await userEvent.click(screen.getByRole("button", { name: "+2 more" }));
        await userEvent.click(screen.getByRole("button", { name: /LO-FI/ }));

        expect(onToggle).toHaveBeenNthCalledWith(1, "SNARE");
        expect(onToggle).toHaveBeenNthCalledWith(2, "LO-FI");
    });

    it("says so when nothing is labeled yet", () => {
        render(<TagLegend tags={[]} painted={[]} onToggle={vi.fn()} emptyCaption={EMPTY_CAPTION} />);

        expect(screen.getByText(EMPTY_CAPTION)).toBeInTheDocument();
    });
});
