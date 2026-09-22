import type { ReactElement } from "react";
import { Link } from "react-router-dom";

/** Marks a control inside an entity row that opens the entity, which the row's own click rule lets through. */
export const OPENS_ENTITY_ATTRIBUTE = "data-opens-entity";

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
        <Link to={href} className="row-open" aria-label={label} {...{ [OPENS_ENTITY_ATTRIBUTE]: "" }}>
            ›
        </Link>
    );
}
