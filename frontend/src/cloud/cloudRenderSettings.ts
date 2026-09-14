import { useMemo } from "react";

import { CATEGORY_ORDER, categoryColorProperty } from "../samples/category";
import { type LabelPaletteParameters, readLabelPaletteParameters } from "../theme/labelPalette";
import { readThemeColor } from "../theme/readThemeColor";
import { readThemeKeyword } from "../theme/readThemeKeyword";
import { readThemeNumber } from "../theme/readThemeNumber";
import { useThemeSignal } from "../theme/useThemeSignal";

export const POINT_SHAPES = ["circle", "square"] as const;
export type PointShape = (typeof POINT_SHAPES)[number];

export const POINT_SCALE_MODES = ["asinh", "linear", "constant"] as const;
export type PointScaleMode = (typeof POINT_SCALE_MODES)[number];

/** How the theme draws the cloud's points themselves. */
export interface PointStyle {
    readonly shape: PointShape;
    /** How large a point is where it names something: a category, or a painted tag. */
    readonly sizePx: number;
    /** How large a point is where it names nothing, so the ground the others sit on reads as grain. */
    readonly substrateSizePx: number;
    /** How opaque a point is where it names something: a category, or a painted tag. */
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
    /** The one color of a batch that carries no categories: the module cloud. */
    readonly point: string;
    readonly selected: string;
    readonly hover: string;
    /** The recessive tone of the points that name nothing. */
    readonly uncategorized: string;
    /** One color per category in `CATEGORY_ORDER`, the uncategorized one in the recessive tone. */
    readonly categories: readonly string[];
    readonly labels: LabelPaletteParameters;
}

/** Everything the current theme says about how the cloud is drawn, read once per theme change. */
export interface CloudRenderSettings {
    readonly point: PointStyle;
    readonly colors: CloudColors;
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

const UNCATEGORIZED_CATEGORY = "uncategorized";
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
    const uncategorized = readColor(UNCATEGORIZED_COLOR);
    return {
        background: readColor(BACKGROUND_COLOR),
        point: readColor(POINT_COLOR),
        selected: readColor(SELECTED_COLOR),
        hover: readColor(HOVER_COLOR),
        uncategorized,
        categories: CATEGORY_ORDER.map((category) =>
            category === UNCATEGORIZED_CATEGORY
                ? uncategorized
                : readThemeColor(categoryColorProperty(category), POINT_COLOR.fallback),
        ),
        labels: readLabelPaletteParameters(),
    };
}

export function readCloudRenderSettings(): CloudRenderSettings {
    return { point: readPointStyle(), colors: readCloudColors() };
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
