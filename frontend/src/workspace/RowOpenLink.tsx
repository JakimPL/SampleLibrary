import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { ROW_LINK_PROPS } from "./rowLinks";

interface RowOpenLinkProps {
    readonly href: string;
    readonly label: string;
}

/**
 * The chevron that opens an entity from its row: shown while the row is pointed at or holds the
 * focus, and always under touch, where a double-click has no equivalent.
 */
export function RowOpenLink({ href, label }: RowOpenLinkProps): ReactElement {
    return (
        <Link to={href} className="row-open" aria-label={label} {...ROW_LINK_PROPS}>
            ›
        </Link>
    );
}
