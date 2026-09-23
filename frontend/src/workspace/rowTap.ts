import type { InputMode } from "../layout/layoutMode";

/** What the tap rule reads of a row's click: whether the row's click rule took it, and where it landed. */
export interface RowClick {
    readonly defaultPrevented: boolean;
    readonly target: EventTarget | null;
}

/** Whether a tap landed on one of the row's own controls, which answer to the tap themselves. */
function isOwnControl(target: EventTarget | null): boolean {
    return target instanceof Element && target.closest("button") !== null;
}

/**
 * Whether a click on a sample row is a finger's tap that plays the row's sample: the row's click
 * rule took it as a highlight, which it marks by preventing the click's default, and it landed
 * beside the row's own buttons, which play or decide on their own.
 */
export function tapPlays(input: InputMode, click: RowClick): boolean {
    return input === "touch" && click.defaultPrevented && !isOwnControl(click.target);
}
