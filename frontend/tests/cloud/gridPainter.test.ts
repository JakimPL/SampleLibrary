import { describe, expect, it } from "vitest";

import type { GridStyle } from "../../src/cloud/cloudRenderSettings";
import { type GridCanvas, paintGrid } from "../../src/cloud/gridPainter";
import { viewTransformOf } from "../../src/cloud/viewTransform";

interface Stroke {
    readonly color: string;
    readonly lineWidth: number;
    readonly segments: readonly (readonly [number, number, number, number])[];
}

/** A 2D context stand-in that records each stroked path: its color, its width and its segments. */
class RecordingCanvas implements GridCanvas {
    strokeStyle: CanvasRenderingContext2D["strokeStyle"] = "";
    lineWidth = 1;
    readonly strokes: Stroke[] = [];
    private segments: (readonly [number, number, number, number])[] = [];
    private start: readonly [number, number] = [0, 0];

    beginPath(): void {
        this.segments = [];
    }

    moveTo(x: number, y: number): void {
        this.start = [x, y];
    }

    lineTo(x: number, y: number): void {
        this.segments.push([this.start[0], this.start[1], x, y]);
    }

    stroke(): void {
        this.strokes.push({
            color: typeof this.strokeStyle === "string" ? this.strokeStyle : "",
            lineWidth: this.lineWidth,
            segments: this.segments,
        });
    }
}

const IDENTITY = new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
const GRID: GridStyle = {
    axes: "both",
    spacingPx: 40,
    lineWidthPx: 1,
    rowColor: "#111111",
    beatColor: "#222222",
    measureColor: "#333333",
    centerColor: "transparent",
};

function paint(grid: GridStyle, devicePixelRatio: number): RecordingCanvas {
    const canvas = new RecordingCanvas();
    const transform = viewTransformOf(IDENTITY, { widthPx: 600, heightPx: 400, devicePixelRatio });
    paintGrid(canvas, transform, grid, { width: 600 * devicePixelRatio, height: 400 * devicePixelRatio });
    return canvas;
}

describe("paintGrid", () => {
    it("strokes one path per rank, rows first and measures last", () => {
        expect(paint(GRID, 1).strokes.map((stroke) => stroke.color)).toEqual(["#111111", "#222222", "#333333"]);
    });

    it("draws full-height vertical lines and full-width horizontal ones across both axes", () => {
        const segments = paint(GRID, 1).strokes.flatMap((stroke) => stroke.segments);

        const vertical = segments.filter(([x1, , x2]) => x1 === x2);
        const horizontal = segments.filter(([, y1, , y2]) => y1 === y2);
        expect(vertical.length).toBeGreaterThan(0);
        expect(horizontal.length).toBeGreaterThan(0);
        expect(vertical.every(([, y1, , y2]) => y1 === 0 && y2 === 400)).toBe(true);
        expect(horizontal.every(([x1, , x2]) => x1 === 0 && x2 === 600)).toBe(true);
    });

    it("draws vertical lines alone, with the center line, the way a tracker's grid does", () => {
        const canvas = paint({ ...GRID, axes: "vertical", centerColor: "#808080" }, 1);
        const gridSegments = canvas.strokes.slice(0, -1).flatMap((stroke) => stroke.segments);
        const center = canvas.strokes[canvas.strokes.length - 1];

        expect(gridSegments.every(([x1, , x2]) => x1 === x2)).toBe(true);
        expect(center?.color).toBe("#808080");
        expect(center?.segments).toEqual([[0, 200.5, 600, 200.5]]);
    });

    it("keeps lines on whole device pixels at a fractional pixel ratio", () => {
        const canvas = paint(GRID, 1.75);
        const lineWidth = canvas.strokes[0]?.lineWidth ?? 0;
        const coordinates = canvas.strokes
            .flatMap((stroke) => stroke.segments)
            .map(([x1, y1, x2]) => (x1 === x2 ? x1 : y1));

        expect(lineWidth).toBe(2);
        expect(coordinates.every((coordinate) => Number.isInteger(coordinate))).toBe(true);
    });

    it("skips a transparent rank and paints nothing for a zero line width", () => {
        expect(paint({ ...GRID, rowColor: "transparent" }, 1).strokes.map((stroke) => stroke.color)).toEqual([
            "#222222",
            "#333333",
        ]);
        expect(paint({ ...GRID, lineWidthPx: 0 }, 1).strokes).toEqual([]);
    });
});
