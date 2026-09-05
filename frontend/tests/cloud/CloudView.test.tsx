import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CloudView } from "../../src/cloud/CloudView";

describe("CloudView", () => {
    it("shows an honest empty state when there are no cloud coordinates yet", () => {
        render(<CloudView points={[]} highlightedSampleHash={null} onSelect={vi.fn()} onFocus={vi.fn()} />);

        expect(screen.getByText("No cloud coordinates yet")).toBeInTheDocument();
        expect(document.querySelector("canvas")).not.toBeInTheDocument();
    });

    it("renders a canvas once points are available", () => {
        render(
            <CloudView
                points={[{ sample_hash: "a".repeat(64), x: 0, y: 0, computed_at: "2026-01-01T00:00:00Z" }]}
                highlightedSampleHash={null}
                onSelect={vi.fn()}
                onFocus={vi.fn()}
            />,
        );

        expect(document.querySelector("canvas")).toBeInTheDocument();
    });
});
