import type { ReactElement } from "react";

import { OptionalLabel } from "./OptionalLabel";

interface DetailHeaderProps {
    readonly name: string;
    readonly placeholder: string;
    readonly hash: string;
}

/**
 * What a detail panel is showing: its name over its hash, in the stack a listing row already names
 * an entity with.
 *
 * One column, so a name of any length leaves everything beneath it where it was, and the hash stays
 * whole and selectable for anyone copying it into a command.
 */
export function DetailHeader({ name, placeholder, hash }: DetailHeaderProps): ReactElement {
    return (
        <header className="detail-header">
            <h2 className="detail-title">
                <OptionalLabel value={name} placeholder={placeholder} />
            </h2>
            <p className="detail-hash mono">{hash}</p>
        </header>
    );
}
