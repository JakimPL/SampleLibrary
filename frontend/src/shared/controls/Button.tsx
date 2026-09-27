import type { ComponentPropsWithoutRef, ReactElement } from "react";

import { buttonClassName, type ButtonOptions } from "./buttonClassName";

type ButtonProps = ButtonOptions & Omit<ComponentPropsWithoutRef<"button">, "type" | "className">;

/**
 * One push button of the shared family. The variant names its intent, the attributes carry its
 * state (`disabled`, `aria-pressed`, `aria-expanded`), and the theme's tokens draw it, so every
 * button in the application looks like the others under the same theme.
 */
export function Button({ variant, icon = false, wide = false, className, ...rest }: ButtonProps): ReactElement {
    const options: ButtonOptions =
        className === undefined ? { variant, icon, wide } : { variant, icon, wide, className };
    return <button type="button" className={buttonClassName(options)} {...rest} />;
}
