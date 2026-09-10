import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { TopLevelTag } from "../../src/cloud/labelColoring";
import { TagLegend } from "../../src/cloud/TagLegend";

const TAGS: readonly TopLevelTag[] = [
    { name: "LO-FI", sampleCount: 33, rank: 4 },
    { name: "SNARE", sampleCount: 21, rank: 0 },
];

describe("TagLegend", () => {
    it("lists every tag with its count, pressed where it is painted", () => {
        render(<TagLegend tags={TAGS} painted={["SNARE"]} onToggle={vi.fn()} />);

        const lofi = screen.getByRole("button", { name: /LO-FI/ });
        const snare = screen.getByRole("button", { name: /SNARE/ });
        expect(lofi).toHaveAttribute("aria-pressed", "false");
        expect(lofi).toHaveTextContent("33");
        expect(snare).toHaveAttribute("aria-pressed", "true");
    });

    it("reports the tag a person toggles", async () => {
        const onToggle = vi.fn();
        render(<TagLegend tags={TAGS} painted={[]} onToggle={onToggle} />);

        await userEvent.click(screen.getByRole("button", { name: /LO-FI/ }));

        expect(onToggle).toHaveBeenCalledWith("LO-FI");
    });

    it("says so when nothing is labeled yet", () => {
        render(<TagLegend tags={[]} painted={[]} onToggle={vi.fn()} />);

        expect(screen.getByText(/No sample carries a label yet/)).toBeInTheDocument();
    });
});
