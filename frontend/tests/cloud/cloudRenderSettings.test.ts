import { afterEach, describe, expect, it } from "vitest";

import { PHONE_POINT_SCALE, readCloudRenderSettings, settingsForLayout } from "../../src/cloud/cloudRenderSettings";

const PROPERTIES = [
    "--cloud-point-shape",
    "--cloud-point-size",
    "--cloud-substrate-size",
    "--cloud-point-opacity",
    "--cloud-substrate-opacity",
    "--cloud-point-size-selected",
    "--cloud-point-outline-width",
    "--cloud-point-scale-mode",
    "--cloud-point-uncategorized",
    "--cloud-marker-size",
    "--cloud-marker-line-width",
    "--cloud-marker-casing-width",
    "--cloud-node-mode",
    "--cloud-node-size",
    "--cloud-node-line-width",
    "--cloud-node-fill-opacity",
    "--cloud-node-substrate-opacity",
    "--cloud-grid-axes",
    "--cloud-grid-spacing",
    "--cloud-grid-line-width",
    "--cloud-grid-row",
    "--cloud-grid-beat",
    "--cloud-grid-measure",
    "--cloud-grid-center",
    "--cloud-glow-opacity",
];

function declare(values: Readonly<Record<string, string>>): void {
    for (const [property, value] of Object.entries(values)) {
        document.documentElement.style.setProperty(property, value);
    }
}

afterEach(() => {
    for (const property of PROPERTIES) {
        document.documentElement.style.removeProperty(property);
    }
});

describe("readCloudRenderSettings", () => {
    it("reads the point style a theme declares", () => {
        declare({
            "--cloud-point-shape": "square",
            "--cloud-point-size": "2",
            "--cloud-substrate-size": "1.5",
            "--cloud-point-opacity": "0.6",
            "--cloud-substrate-opacity": "0.25",
            "--cloud-point-size-selected": "3",
            "--cloud-point-outline-width": "1",
            "--cloud-point-scale-mode": "constant",
        });

        expect(readCloudRenderSettings().point).toEqual({
            shape: "square",
            sizePx: 2,
            substrateSizePx: 1.5,
            opacity: 0.6,
            substrateOpacity: 0.25,
            selectedExtraSizePx: 3,
            outlineWidthPx: 1,
            scaleMode: "constant",
        });
    });

    it("holds opacities within what the scatterplot draws and the selected point at least a pixel larger", () => {
        declare({ "--cloud-point-opacity": "0", "--cloud-substrate-opacity": "4", "--cloud-point-size-selected": "0" });

        const { point } = readCloudRenderSettings();

        expect(point.opacity).toBeGreaterThan(0);
        expect(point.substrateOpacity).toBe(1);
        expect(point.selectedExtraSizePx).toBeGreaterThanOrEqual(1);
    });

    it("paints the points that name nothing in the substrate's tone", () => {
        declare({ "--cloud-point-uncategorized": "#123456" });

        const { colors } = readCloudRenderSettings();

        expect(colors.uncategorized).toBe("#123456");
    });

    it("reads the marker and node styles a theme declares", () => {
        declare({
            "--cloud-marker-size": "9",
            "--cloud-marker-line-width": "2",
            "--cloud-marker-casing-width": "0",
            "--cloud-node-mode": "always",
            "--cloud-node-size": "5",
            "--cloud-node-line-width": "1",
            "--cloud-node-fill-opacity": "0.4",
            "--cloud-node-substrate-opacity": "0.5",
        });

        const { marker, node } = readCloudRenderSettings();

        expect(marker).toEqual({ sizePx: 9, lineWidthPx: 2, casingWidthPx: 0 });
        expect(node).toEqual({ mode: "always", sizePx: 5, lineWidthPx: 1, fillOpacity: 0.4, substrateOpacity: 0.5 });
    });

    it("reads the grid a theme declares", () => {
        declare({
            "--cloud-grid-axes": "vertical",
            "--cloud-grid-spacing": "36",
            "--cloud-grid-line-width": "1",
            "--cloud-grid-row": "#333",
            "--cloud-grid-beat": "#555",
            "--cloud-grid-measure": "#808080",
            "--cloud-grid-center": "#8a8a8a",
        });

        expect(readCloudRenderSettings().grid).toEqual({
            axes: "vertical",
            spacingPx: 36,
            lineWidthPx: 1,
            rowColor: "#333",
            beatColor: "#555",
            measureColor: "#808080",
            centerColor: "#8a8a8a",
        });
    });

    it("holds node and glow opacities to the unit interval", () => {
        declare({
            "--cloud-node-fill-opacity": "-1",
            "--cloud-node-substrate-opacity": "3",
            "--cloud-glow-opacity": "2",
        });

        const { node, glow } = readCloudRenderSettings();

        expect(node.fillOpacity).toBe(0);
        expect(node.substrateOpacity).toBe(1);
        expect(glow.opacity).toBe(1);
    });
});

describe("settingsForLayout", () => {
    it("draws the scatterplot's points smaller on a phone, where the cloud holds the same points in a third of the area", () => {
        const settings = readCloudRenderSettings();

        const phone = settingsForLayout(settings, "phone");

        expect(phone.point.sizePx).toBeCloseTo(settings.point.sizePx * PHONE_POINT_SCALE, 5);
        expect(phone.point.substrateSizePx).toBeCloseTo(settings.point.substrateSizePx * PHONE_POINT_SCALE, 5);
        expect(phone.point.opacity).toBe(settings.point.opacity);
    });

    it("leaves the theme's own sizes to the workspace", () => {
        const settings = readCloudRenderSettings();

        expect(settingsForLayout(settings, "workspace")).toBe(settings);
    });
});
