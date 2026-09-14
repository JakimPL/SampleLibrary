import { afterEach, describe, expect, it } from "vitest";

import { readCloudRenderSettings } from "../../src/cloud/cloudRenderSettings";
import { categoryIndex } from "../../src/samples/category";

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
    "--category-kick",
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

    it("paints each category in its own color and the uncategorized one in the substrate's tone", () => {
        declare({ "--category-kick": "#abcdef", "--cloud-point-uncategorized": "#123456" });

        const { colors } = readCloudRenderSettings();

        expect(colors.categories[categoryIndex("kick")]).toBe("#abcdef");
        expect(colors.categories[categoryIndex("uncategorized")]).toBe("#123456");
        expect(colors.uncategorized).toBe("#123456");
    });
});
