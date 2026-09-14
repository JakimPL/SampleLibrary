import { boundsOf } from "../src/cloud/geometry";

export interface PlanarPoint {
    readonly x: number;
    readonly y: number;
}

export interface DensifyOptions<Point extends PlanarPoint> {
    /** How many points to answer with, the given ones included. */
    readonly targetCount: number;
    readonly seed: number;
    /** How large a cluster a point grows, relative to the other points'. */
    readonly weightOf: (point: Point) => number;
}

const CONGRUENTIAL_MULTIPLIER = 1664525;
const CONGRUENTIAL_INCREMENT = 1013904223;
const CONGRUENTIAL_MODULUS = 4294967296;
const BOX_MULLER_SCALE = 2;
const FULL_TURN_RADIANS = 6.283185307179586;
const CLUSTER_WEIGHT_SPREAD = 1.2;
const CLUSTER_SIGMA_FRACTION = 0.06;
const CLUSTER_SIGMA_SPREAD = 0.5;
const OUTLIER_SHARE = 0.01;
const OUTLIER_MARGIN_FRACTION = 0.15;
const FALLBACK_SPAN = 1;
// Kept equal to COORDINATE_DECIMALS in src/sampleserver/routers/cloud.py.
const COORDINATE_SCALE = 10000;

type Random = () => number;

interface Box {
    readonly minimumX: number;
    readonly maximumX: number;
    readonly minimumY: number;
    readonly maximumY: number;
}

interface Cluster<Point extends PlanarPoint> {
    readonly parent: Point;
    readonly weight: number;
    readonly sigmaX: number;
    readonly sigmaY: number;
}

/** A linear congruential generator: one seed, one cloud, so screenshots taken across reloads compare. */
function createRandom(seed: number): Random {
    let state = seed % CONGRUENTIAL_MODULUS;
    return (): number => {
        state = (state * CONGRUENTIAL_MULTIPLIER + CONGRUENTIAL_INCREMENT) % CONGRUENTIAL_MODULUS;
        return state / CONGRUENTIAL_MODULUS;
    };
}

function gaussian(random: Random): number {
    const magnitude = Math.sqrt(-BOX_MULLER_SCALE * Math.log(1 - random()));
    return magnitude * Math.cos(FULL_TURN_RADIANS * random());
}

function boxOf(points: readonly PlanarPoint[]): Box {
    const horizontal = boundsOf(points, (point) => point.x);
    const vertical = boundsOf(points, (point) => point.y);
    return {
        minimumX: horizontal.minimum,
        maximumX: horizontal.maximum,
        minimumY: vertical.minimum,
        maximumY: vertical.maximum,
    };
}

function spanOf(box: Box): number {
    const span = Math.max(box.maximumX - box.minimumX, box.maximumY - box.minimumY);
    return span > 0 ? span : FALLBACK_SPAN;
}

function clustersOf<Point extends PlanarPoint>(
    points: readonly Point[],
    span: number,
    weightOf: (point: Point) => number,
    random: Random,
): Cluster<Point>[] {
    const sigma = CLUSTER_SIGMA_FRACTION * span;
    return points.map((parent) => ({
        parent,
        weight: weightOf(parent) * Math.exp(CLUSTER_WEIGHT_SPREAD * gaussian(random)),
        sigmaX: sigma * Math.exp(CLUSTER_SIGMA_SPREAD * gaussian(random)),
        sigmaY: sigma * Math.exp(CLUSTER_SIGMA_SPREAD * gaussian(random)),
    }));
}

/**
 * Splits `cloneCount` across the clusters in proportion to their weights, the last cluster taking
 * the rounding remainder so the counts add up to `cloneCount` exactly.
 */
function cloneCounts(weights: readonly number[], cloneCount: number): number[] {
    const total = weights.reduce((sum, weight) => sum + weight, 0);
    let cumulative = 0;
    let allocated = 0;
    return weights.map((weight, index) => {
        cumulative += weight;
        const upTo = index === weights.length - 1 ? cloneCount : Math.floor((cloneCount * cumulative) / total);
        const count = upTo - allocated;
        allocated = upTo;
        return count;
    });
}

function roundCoordinate(value: number): number {
    return Math.round(value * COORDINATE_SCALE) / COORDINATE_SCALE;
}

function uniformBetween(low: number, high: number, random: Random): number {
    return low + random() * (high - low);
}

function outlierOf<Point extends PlanarPoint>(parent: Point, box: Box, random: Random): Point {
    const marginX = OUTLIER_MARGIN_FRACTION * (box.maximumX - box.minimumX);
    const marginY = OUTLIER_MARGIN_FRACTION * (box.maximumY - box.minimumY);
    return {
        ...parent,
        x: roundCoordinate(uniformBetween(box.minimumX - marginX, box.maximumX + marginX, random)),
        y: roundCoordinate(uniformBetween(box.minimumY - marginY, box.maximumY + marginY, random)),
    };
}

function cloneOf<Point extends PlanarPoint>(cluster: Cluster<Point>, box: Box, random: Random): Point {
    if (random() < OUTLIER_SHARE) {
        return outlierOf(cluster.parent, box, random);
    }
    return {
        ...cluster.parent,
        x: roundCoordinate(cluster.parent.x + gaussian(random) * cluster.sigmaX),
        y: roundCoordinate(cluster.parent.y + gaussian(random) * cluster.sigmaY),
    };
}

function shuffled<Item>(items: readonly Item[], random: Random): Item[] {
    const result = [...items];
    for (let index = result.length - 1; index > 0; index -= 1) {
        const other = Math.floor(random() * (index + 1));
        const held = result[index];
        const swapped = result[other];
        if (held !== undefined && swapped !== undefined) {
            result[index] = swapped;
            result[other] = held;
        }
    }
    return result;
}

/**
 * Every given point first and unchanged, then clones of them: each point grows a Gaussian cluster
 * whose size follows its weight and whose reach is a fraction of the cloud's span, both spread
 * log-normally so a few dense cores stand among many sparse blobs the way a real library's
 * clusters do, with one clone in a hundred thrown to the margins as an outlier. The clones arrive
 * shuffled, so every category interleaves with the others in draw order, and the same seed gives the
 * same cloud on every call.
 */
export function densifyPoints<Point extends PlanarPoint>(
    points: readonly Point[],
    options: DensifyOptions<Point>,
): readonly Point[] {
    if (points.length === 0 || options.targetCount <= points.length) {
        return points;
    }
    const random = createRandom(options.seed);
    const box = boxOf(points);
    const clusters = clustersOf(points, spanOf(box), options.weightOf, random);
    const counts = cloneCounts(
        clusters.map((cluster) => cluster.weight),
        options.targetCount - points.length,
    );
    const clones: Point[] = [];
    clusters.forEach((cluster, index) => {
        const count = counts[index] ?? 0;
        for (let made = 0; made < count; made += 1) {
            clones.push(cloneOf(cluster, box, random));
        }
    });
    return [...points, ...shuffled(clones, random)];
}

/** The point count an environment value names, or null when it names none. */
export function parseDensifyTarget(text: string | undefined): number | null {
    if (text === undefined || text.trim() === "") {
        return null;
    }
    const count = Number(text);
    return Number.isInteger(count) && count > 0 ? count : null;
}
