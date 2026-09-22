export type LayoutMode = "phone" | "workspace";

export type InputMode = "touch" | "pointer";

export interface LayoutSignal {
    readonly layout: LayoutMode;
    readonly input: InputMode;
}

export const WORKSPACE_MIN_WIDTH_PX = 768;
export const WORKSPACE_MIN_HEIGHT_PX = 560;

/** Matches a viewport too narrow or too short for the workspace; a landscape phone matches through its height. */
export const PHONE_MEDIA_QUERY = `(width < ${String(WORKSPACE_MIN_WIDTH_PX)}px), (height < ${String(WORKSPACE_MIN_HEIGHT_PX)}px)`;
export const COARSE_POINTER_MEDIA_QUERY = "(pointer: coarse)";

/** The shell a viewport gets: the phone shell wherever the phone query matches, the workspace everywhere else. */
export function layoutModeOf(phoneMatches: boolean): LayoutMode {
    return phoneMatches ? "phone" : "workspace";
}

/**
 * How the person points: touch while the primary pointer is coarse, which is what needs the larger
 * targets and loses hover previews. Hover alone says nothing: a desktop with no mouse attached, and
 * a headless browser, report no hover while a finger is nowhere in sight.
 */
export function inputModeOf(coarsePointer: boolean): InputMode {
    return coarsePointer ? "touch" : "pointer";
}
