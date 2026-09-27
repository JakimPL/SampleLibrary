import { classNames } from "../classNames";

/** What a button is for: the one next step, another action, or a tool or menu row that stays quiet until hovered. */
export type ButtonVariant = "primary" | "secondary" | "quiet";

export interface ButtonOptions {
    readonly variant: ButtonVariant;
    /** A square button holding one glyph, at the control height on both sides. */
    readonly icon?: boolean;
    /** A button as wide as its row with its text at the start: a menu row or a sheet's action. */
    readonly wide?: boolean;
    readonly className?: string;
}

const VARIANT_CLASSES: Readonly<Record<ButtonVariant, string | null>> = {
    primary: "button-primary",
    secondary: null,
    quiet: "button-quiet",
};

/**
 * The classes of one push button of the shared family, for the elements that act as buttons
 * without being one: a `Link` standing in a row of buttons, or a menu's `summary`. `Button`
 * takes the same options for a real button.
 */
export function buttonClassName({ variant, icon = false, wide = false, className }: ButtonOptions): string {
    return classNames("button", VARIANT_CLASSES[variant], icon && "button-icon", wide && "button-wide", className);
}
