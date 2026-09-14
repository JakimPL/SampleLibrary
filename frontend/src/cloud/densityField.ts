import type { NodeGeometry } from "./nodeGeometry";
import type { DataBounds } from "./viewTransform";

/**
 * How many points fall into each cell of a square grid laid over part of the data space, with the
 * sum of their colors' channels, rows running from the domain's top edge down.
 */
export interface DensityField {
    readonly resolution: number;
    readonly domain: DataBounds;
    readonly counts: Float32Array;
    readonly red: Float32Array;
    readonly green: Float32Array;
    readonly blue: Float32Array;
}

const COORDINATES_PER_POINT = 2;
const SIDES_OF_A_CELL = 2;
const BYTES_PER_COLOR = 4;
const GREEN_OFFSET = 1;
const BLUE_OFFSET = 2;
const CHANNEL_MAXIMUM = 255;
const ALPHA_OFFSET = 3;

/**
 * Counts every node of `geometry` into the cell of `domain` it falls in, adding its palette color
 * (one RGBA byte quadruple per slot) to the cell's color sums. Nodes outside the domain, and those in
 * `excludedSlot` when one is named, stay out of the field.
 */
export function accumulateDensity(
    geometry: NodeGeometry,
    palette: Uint8Array,
    resolution: number,
    domain: DataBounds,
    excludedSlot: number | null,
): DensityField {
    const cells = resolution * resolution;
    const field: DensityField = {
        resolution,
        domain,
        counts: new Float32Array(cells),
        red: new Float32Array(cells),
        green: new Float32Array(cells),
        blue: new Float32Array(cells),
    };
    const width = domain.maximumX - domain.minimumX;
    const height = domain.maximumY - domain.minimumY;
    for (let node = 0; node < geometry.count; node += 1) {
        const x = geometry.positions[node * COORDINATES_PER_POINT] ?? Number.NaN;
        const y = geometry.positions[node * COORDINATES_PER_POINT + 1] ?? Number.NaN;
        const slot = geometry.slots[node] ?? 0;
        const column = Math.floor(((x - domain.minimumX) / width) * resolution);
        const row = Math.floor(((domain.maximumY - y) / height) * resolution);
        if (slot === excludedSlot || column < 0 || column >= resolution || row < 0 || row >= resolution) {
            continue;
        }
        const cell = row * resolution + column;
        const colorOffset = slot * BYTES_PER_COLOR;
        field.counts[cell] = (field.counts[cell] ?? 0) + 1;
        field.red[cell] = (field.red[cell] ?? 0) + (palette[colorOffset] ?? 0);
        field.green[cell] = (field.green[cell] ?? 0) + (palette[colorOffset + GREEN_OFFSET] ?? 0);
        field.blue[cell] = (field.blue[cell] ?? 0) + (palette[colorOffset + BLUE_OFFSET] ?? 0);
    }
    return field;
}

/**
 * One pass of a box blur along rows or along columns: each cell becomes the mean of itself and the
 * `radius` cells on either side, the grid's edge cell standing in past its end.
 */
function boxBlurPass(values: Float32Array, resolution: number, radius: number, alongRows: boolean): Float32Array {
    const blurred = new Float32Array(values.length);
    const windowSize = radius * SIDES_OF_A_CELL + 1;
    for (let line = 0; line < resolution; line += 1) {
        for (let position = 0; position < resolution; position += 1) {
            let sum = 0;
            for (let offset = -radius; offset <= radius; offset += 1) {
                const neighbor = Math.min(resolution - 1, Math.max(0, position + offset));
                const cell = alongRows ? line * resolution + neighbor : neighbor * resolution + line;
                sum += values[cell] ?? 0;
            }
            const cell = alongRows ? line * resolution + position : position * resolution + line;
            blurred[cell] = sum / windowSize;
        }
    }
    return blurred;
}

function blurChannel(values: Float32Array, resolution: number, radius: number, passes: number): Float32Array {
    let blurred = values;
    for (let pass = 0; pass < passes; pass += 1) {
        blurred = boxBlurPass(boxBlurPass(blurred, resolution, radius, true), resolution, radius, false);
    }
    return blurred;
}

/**
 * The field softened by `passes` rounds of a box blur of `radius` cells along rows and then columns,
 * which together approach a Gaussian: a dense patch spreads into a glow that fades with distance.
 * Every channel blurs alike, so a cell's average color stays the average of the points around it.
 */
export function blurDensity(field: DensityField, radius: number, passes: number): DensityField {
    return {
        ...field,
        counts: blurChannel(field.counts, field.resolution, radius, passes),
        red: blurChannel(field.red, field.resolution, radius, passes),
        green: blurChannel(field.green, field.resolution, radius, passes),
        blue: blurChannel(field.blue, field.resolution, radius, passes),
    };
}

/**
 * One RGBA byte quadruple per cell, row by row from the top: each cell in the average color of the
 * points around it, as opaque as `opacity` times its count on a logarithmic scale up to the densest
 * cell's. A library's clusters differ in density by orders of magnitude, and the logarithm keeps a
 * sparse cluster's glow in view beside the densest one's.
 */
export function glowPixels(field: DensityField, opacity: number): Uint8ClampedArray {
    const pixels = new Uint8ClampedArray(field.counts.length * BYTES_PER_COLOR);
    const densest = field.counts.reduce((maximum, count) => Math.max(maximum, count), 0);
    if (densest <= 0) {
        return pixels;
    }
    const scale = Math.log1p(densest);
    field.counts.forEach((count, cell) => {
        if (count <= 0) {
            return;
        }
        const offset = cell * BYTES_PER_COLOR;
        pixels[offset] = (field.red[cell] ?? 0) / count;
        pixels[offset + GREEN_OFFSET] = (field.green[cell] ?? 0) / count;
        pixels[offset + BLUE_OFFSET] = (field.blue[cell] ?? 0) / count;
        pixels[offset + ALPHA_OFFSET] = (Math.log1p(count) / scale) * opacity * CHANNEL_MAXIMUM;
    });
    return pixels;
}
