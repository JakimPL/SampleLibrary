import type { InputMode } from "../layout/layoutMode";

/** Kept equal to `--row-height` in styles.css under each input mode, since the virtualizer places a listing's rows by it. */
export const TABLE_ROW_HEIGHT_BY_INPUT: Readonly<Record<InputMode, number>> = { pointer: 40, touch: 52 };

export const TABLE_OVERSCAN_ROWS = 12;

export const TABLE_INITIAL_VIEWPORT_HEIGHT_PX = 480;
