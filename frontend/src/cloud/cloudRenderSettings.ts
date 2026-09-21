import { useMemo } from "react";

import { type LabelPaletteParameters, readLabelPaletteParameters } from "../theme/labelPalette";
import { readThemeColor } from "../theme/readThemeColor";
import { readThemeKeyword } from "../theme/readThemeKeyword";
import { readThemeNumber } from "../theme/readThemeNumber";
import { useThemeSignal } from "../theme/useThemeSignal";

export const POINT_SHAPES = ["circle", "square"] as const;
export type PointShape = (typeof POINT_SHAPES)[number];

export const POINT_SCALE_MODES = ["asinh", "linear", "constant"] as const;
export type PointScaleMode = (typeof POINT_SCALE_MODES)[number];

/** When the node layer draws every point as a hollow marker: at every zoom, or once a view holds few enough points. */
export const NODE_MODES = ["always", "detail"] as const;
export type NodeMode = (typeof NODE_MODES)[number];

/** Which lines the grid draws: across both axes, or the vertical ones alone the way a tracker's time grid does. */
export const GRID_AXES = ["both", "vertical"] as const;
export type GridAxes = (typeof GRID_AXES)[number];

/** How the theme draws the cloud's points themselves. */
export interface PointStyle {
    readonly shape: PointShape;
    /** How large a point is where it names something: a painted tag. */
    readonly sizePx: number;
    /** How large a point is where it names nothing, so the ground the others sit on reads as grain. */
    readonly substrateSizePx: number;
    /** How opaque a point is where it names something: a painted tag. */
    readonly opacity: number;
    /** How opaque a point is where it names nothing, so the ground the others sit on shows its density. */
    readonly substrateOpacity: number;
    /** How much larger than its neighbors the selected point draws. */
    readonly selectedExtraSizePx: number;
    readonly outlineWidthPx: number;
    /** How a point grows as the view zooms in. */
    readonly scaleMode: PointScaleMode;
}

export interface CloudColors {
    readonly background: string;
    /** The one color of the module cloud, whose points carry no tags. */
    readonly point: string;
    readonly selected: string;
    readonly hover: string;
    /** The recessive tone of the points that name nothing. */
    readonly uncategorized: string;
    readonly labels: LabelPaletteParameters;
}

/** How the theme draws the markers over single points: the hovered, the selected, and a morph's two ends. */
export interface MarkerStyle {
    /** The marker's outer size, edge to edge. */
    readonly sizePx: number;
    readonly lineWidthPx: number;
    /** How far the background-colored band beneath a marker's stroke reaches past it on either side. */
    readonly casingWidthPx: number;
}

/** How the theme draws the node layer: every point as a hollow marker of one size at any zoom. */
export interface NodeStyle {
    readonly mode: NodeMode;
    readonly sizePx: number;
    readonly lineWidthPx: number;
    /** How opaque a marker's inside is, zero leaving it hollow. */
    readonly fillOpacity: number;
    /** How opaque the substrate's markers are, the named points' being fully opaque. */
    readonly substrateOpacity: number;
}

/** How the theme draws the grid beneath the points, its lines ranked as rows, beats and measures. */
export interface GridStyle {
    readonly axes: GridAxes;
    /** The least distance between neighboring lines, which the grid keeps under two of these. */
    readonly spacingPx: number;
    readonly lineWidthPx: number;
    readonly rowColor: string;
    readonly beatColor: string;
    readonly measureColor: string;
    /** The horizontal line through the data's zero, "transparent" leaving it out. */
    readonly centerColor: string;
}

/** How the theme draws the density glow beneath the points. */
export interface GlowStyle {
    /** How opaque the densest glow is, zero turning the glow off. */
    readonly opacity: number;
}

/** Everything the current theme says about how the cloud is drawn, read once per theme change. */
export interface CloudRenderSettings {
    readonly point: PointStyle;
    readonly colors: CloudColors;
    readonly marker: MarkerStyle;
    readonly node: NodeStyle;
    readonly grid: GridStyle;
    readonly glow: GlowStyle;
}

interface Token<Value> {
    readonly property: string;
    /** The value under a stylesheet that declares none, matching the light theme's own. */
    readonly fallback: Value;
}

const SHAPE: Token<PointShape> = { property: "--cloud-point-shape", fallback: "circle" };
const SIZE: Token<number> = { property: "--cloud-point-size", fallback: 2.5 };
const SUBSTRATE_SIZE: Token<number> = { property: "--cloud-substrate-size", fallback: 1.8 };
const OPACITY: Token<number> = { property: "--cloud-point-opacity", fallback: 0.9 };
const SUBSTRATE_OPACITY: Token<number> = { property: "--cloud-substrate-opacity", fallback: 0.6 };
const SELECTED_EXTRA_SIZE: Token<number> = { property: "--cloud-point-size-selected", fallback: 2 };
const OUTLINE_WIDTH: Token<number> = { property: "--cloud-point-outline-width", fallback: 0 };
const SCALE_MODE: Token<PointScaleMode> = { property: "--cloud-point-scale-mode", fallback: "asinh" };
const BACKGROUND_COLOR: Token<string> = { property: "--cloud-bg", fallback: "#f4f5f7" };
const POINT_COLOR: Token<string> = { property: "--cloud-point", fallback: "#1b1f26" };
const SELECTED_COLOR: Token<string> = { property: "--cloud-point-selected", fallback: "#a8690f" };
const HOVER_COLOR: Token<string> = { property: "--cloud-hover-color", fallback: "#1b1f26" };
const UNCATEGORIZED_COLOR: Token<string> = { property: "--cloud-point-uncategorized", fallback: "#d5d4ce" };
const MARKER_SIZE: Token<number> = { property: "--cloud-marker-size", fallback: 13 };
const MARKER_LINE_WIDTH: Token<number> = { property: "--cloud-marker-line-width", fallback: 1.5 };
const MARKER_CASING_WIDTH: Token<number> = { property: "--cloud-marker-casing-width", fallback: 1.5 };
const NODE_MODE: Token<NodeMode> = { property: "--cloud-node-mode", fallback: "detail" };
const NODE_SIZE: Token<number> = { property: "--cloud-node-size", fallback: 7 };
const NODE_LINE_WIDTH: Token<number> = { property: "--cloud-node-line-width", fallback: 1 };
const NODE_FILL_OPACITY: Token<number> = { property: "--cloud-node-fill-opacity", fallback: 0.2 };
const NODE_SUBSTRATE_OPACITY: Token<number> = { property: "--cloud-node-substrate-opacity", fallback: 0.8 };
const GRID_AXES_TOKEN: Token<GridAxes> = { property: "--cloud-grid-axes", fallback: "both" };
const GRID_SPACING: Token<number> = { property: "--cloud-grid-spacing", fallback: 44 };
const GRID_LINE_WIDTH: Token<number> = { property: "--cloud-grid-line-width", fallback: 1 };
const GRID_ROW_COLOR: Token<string> = { property: "--cloud-grid-row", fallback: "rgb(27 31 38 / 3.5%)" };
const GRID_BEAT_COLOR: Token<string> = { property: "--cloud-grid-beat", fallback: "rgb(27 31 38 / 6%)" };
const GRID_MEASURE_COLOR: Token<string> = { property: "--cloud-grid-measure", fallback: "rgb(27 31 38 / 10%)" };
const GRID_CENTER_COLOR: Token<string> = { property: "--cloud-grid-center", fallback: "transparent" };
const GLOW_OPACITY: Token<number> = { property: "--cloud-glow-opacity", fallback: 0 };
const MINIMUM_GRID_SPACING_PX = 4;

const MINIMUM_OPACITY = 0.01;
const MINIMUM_SELECTED_EXTRA_SIZE_PX = 1;

function readColor(token: Token<string>): string {
    return readThemeColor(token.property, token.fallback);
}

function readNumber(token: Token<number>): number {
    return readThemeNumber(token.property, token.fallback);
}

/** An opacity held to the range the scatterplot accepts, which refuses zero. */
function readOpacity(token: Token<number>): number {
    return Math.min(1, Math.max(MINIMUM_OPACITY, readNumber(token)));
}

/**
 * The selected point's extra size, held to at least one pixel: the scatterplot keeps its previous
 * extra size when handed zero, so one pixel is the smallest size a theme can reliably ask for.
 */
function readSelectedExtraSize(): number {
    return Math.max(MINIMUM_SELECTED_EXTRA_SIZE_PX, readNumber(SELECTED_EXTRA_SIZE));
}

function readPointStyle(): PointStyle {
    return {
        shape: readThemeKeyword(SHAPE.property, POINT_SHAPES, SHAPE.fallback),
        sizePx: readNumber(SIZE),
        substrateSizePx: readNumber(SUBSTRATE_SIZE),
        opacity: readOpacity(OPACITY),
        substrateOpacity: readOpacity(SUBSTRATE_OPACITY),
        selectedExtraSizePx: readSelectedExtraSize(),
        outlineWidthPx: Math.max(0, readNumber(OUTLINE_WIDTH)),
        scaleMode: readThemeKeyword(SCALE_MODE.property, POINT_SCALE_MODES, SCALE_MODE.fallback),
    };
}

function readCloudColors(): CloudColors {
    return {
        background: readColor(BACKGROUND_COLOR),
        point: readColor(POINT_COLOR),
        selected: readColor(SELECTED_COLOR),
        hover: readColor(HOVER_COLOR),
        uncategorized: readColor(UNCATEGORIZED_COLOR),
        labels: readLabelPaletteParameters(),
    };
}

function readMarkerStyle(): MarkerStyle {
    return {
        sizePx: Math.max(0, readNumber(MARKER_SIZE)),
        lineWidthPx: Math.max(0, readNumber(MARKER_LINE_WIDTH)),
        casingWidthPx: Math.max(0, readNumber(MARKER_CASING_WIDTH)),
    };
}

function readUnitInterval(token: Token<number>): number {
    return Math.min(1, Math.max(0, readNumber(token)));
}

function readNodeStyle(): NodeStyle {
    return {
        mode: readThemeKeyword(NODE_MODE.property, NODE_MODES, NODE_MODE.fallback),
        sizePx: Math.max(1, readNumber(NODE_SIZE)),
        lineWidthPx: Math.max(0, readNumber(NODE_LINE_WIDTH)),
        fillOpacity: readUnitInterval(NODE_FILL_OPACITY),
        substrateOpacity: readUnitInterval(NODE_SUBSTRATE_OPACITY),
    };
}

function readGridStyle(): GridStyle {
    return {
        axes: readThemeKeyword(GRID_AXES_TOKEN.property, GRID_AXES, GRID_AXES_TOKEN.fallback),
        spacingPx: Math.max(MINIMUM_GRID_SPACING_PX, readNumber(GRID_SPACING)),
        lineWidthPx: Math.max(0, readNumber(GRID_LINE_WIDTH)),
        rowColor: readColor(GRID_ROW_COLOR),
        beatColor: readColor(GRID_BEAT_COLOR),
        measureColor: readColor(GRID_MEASURE_COLOR),
        centerColor: readColor(GRID_CENTER_COLOR),
    };
}

export function readCloudRenderSettings(): CloudRenderSettings {
    return {
        point: readPointStyle(),
        colors: readCloudColors(),
        marker: readMarkerStyle(),
        node: readNodeStyle(),
        grid: readGridStyle(),
        glow: { opacity: readUnitInterval(GLOW_OPACITY) },
    };
}

/**
 * The cloud's render settings, read again whenever `useThemeSignal` reports the resolved theme
 * could have changed. The object keeps its identity between theme changes, so an effect that
 * depends on it re-applies the theme exactly when there is a new one to apply.
 */
export function useCloudRenderSettings(): CloudRenderSettings {
    const themeSignal = useThemeSignal();
    return useMemo(readCloudRenderSettings, [themeSignal.preference, themeSignal.systemVersion]);
}
