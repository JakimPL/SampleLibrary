import type { ReactElement } from "react";

import { ICON_PATHS, type IconName } from "./iconPaths";

interface IconProps {
    readonly name: IconName;
    /** What a screen reader hears; `null` marks the icon as decoration beside a visible label. */
    readonly label: string | null;
}

const ICON_VIEWBOX = "0 0 24 24";
const ICON_STROKE_WIDTH = 2;

/** One of the shell's line icons, sized to the surrounding text. */
export function Icon({ name, label }: IconProps): ReactElement {
    return (
        <svg
            className="icon"
            viewBox={ICON_VIEWBOX}
            width="1em"
            height="1em"
            fill="none"
            stroke="currentColor"
            strokeWidth={ICON_STROKE_WIDTH}
            strokeLinecap="round"
            strokeLinejoin="round"
            role={label === null ? undefined : "img"}
            aria-label={label ?? undefined}
            aria-hidden={label === null ? true : undefined}
        >
            <path d={ICON_PATHS[name]} />
        </svg>
    );
}
