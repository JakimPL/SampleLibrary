import type { ReactElement } from "react";

interface FolderPathProps {
    readonly path: string | null;
    /** What the line reads while it names no folder. */
    readonly placeholder: string;
}

/**
 * A folder's path on one line whatever its length. A path too long for the line loses its start, so
 * the folder's own name stays in view, and the whole path shows on hover.
 */
export function FolderPath({ path, placeholder }: FolderPathProps): ReactElement {
    return (
        <span className="path-line mono" data-empty={path === null} title={path ?? undefined}>
            <bdi>{path ?? placeholder}</bdi>
        </span>
    );
}
