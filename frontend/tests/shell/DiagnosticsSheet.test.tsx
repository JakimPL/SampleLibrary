import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useCloudDotsStore } from "../../src/cloud/cloudDotsStore";
import type { FloatRenderingSupport } from "../../src/cloud/floatRendering";
import { DiagnosticsSheet } from "../../src/shell/DiagnosticsSheet";

const WITHOUT_BLENDING: FloatRenderingSupport = {
    webgl: true,
    textureFloat: true,
    colorBufferFloat: true,
    floatBlend: false,
    renderer: "Apple GPU",
};

describe("DiagnosticsSheet", () => {
    it("states what the browser's WebGL supports and how the points draw as a result", () => {
        render(<DiagnosticsSheet support={WITHOUT_BLENDING} onClose={vi.fn()} />);

        expect(screen.getByRole("dialog", { name: "Diagnostics" })).toBeInTheDocument();
        expect(screen.getByText("Apple GPU")).toBeInTheDocument();
        expect(screen.getByText("Float blending").nextElementSibling).toHaveTextContent("no");
        expect(screen.getByText(/plain dots stand in/)).toBeInTheDocument();
        expect(screen.getByText("Layout").nextElementSibling).toHaveTextContent("workspace, pointer");
    });

    it("says nothing draws without WebGL", () => {
        render(
            <DiagnosticsSheet
                support={{
                    webgl: false,
                    textureFloat: false,
                    colorBufferFloat: false,
                    floatBlend: false,
                    renderer: null,
                }}
                onClose={vi.fn()}
            />,
        );

        expect(screen.getByText("WebGL").nextElementSibling).toHaveTextContent("unavailable");
        expect(screen.getByText("nothing draws without WebGL")).toBeInTheDocument();
    });

    it("lets a person choose plain dots, and closes from its scrim", () => {
        const onClose = vi.fn();
        render(<DiagnosticsSheet support={WITHOUT_BLENDING} onClose={onClose} />);
        expect(screen.getByRole("radio", { name: "As the browser allows" })).toBeChecked();

        fireEvent.click(screen.getByRole("radio", { name: "Plain dots" }));

        expect(useCloudDotsStore.getState().dots).toBe("plain");
        expect(screen.getByRole("radio", { name: "Plain dots" })).toBeChecked();
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        expect(onClose).toHaveBeenCalled();
    });
});
