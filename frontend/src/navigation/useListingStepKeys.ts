import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { type ListingNeighbors, useListingNeighbors } from "../workspace/listingOrderStore";
import { entityRoute } from "../workspace/useEntityRowInteractions";
import { entityOf, type ShellView } from "./shellView";

const PREVIOUS_KEY = "ArrowLeft";
const NEXT_KEY = "ArrowRight";

/** The hash a step key names within the listing, or `null` for any other key or an edge of the listing. */
export function steppedHash(event: KeyboardEvent, neighbors: ListingNeighbors): string | null {
    if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return null;
    }
    switch (event.key) {
        case PREVIOUS_KEY:
            return neighbors.previous;
        case NEXT_KEY:
            return neighbors.next;
        default:
            return null;
    }
}

/**
 * Alt+Left and Alt+Right walk the listing from the entity the address names, each step replacing
 * the address so a run through many samples stays one step back from the list they came from.
 */
export function useListingStepKeys(view: ShellView): void {
    const navigate = useNavigate();
    const entity = entityOf(view);
    const neighbors = useListingNeighbors(entity);

    useEffect(() => {
        if (entity === null) {
            return undefined;
        }
        function handleKeyDown(event: KeyboardEvent): void {
            const hash = steppedHash(event, neighbors);
            if (hash === null || entity === null) {
                return;
            }
            event.preventDefault();
            void navigate(entityRoute({ kind: entity.kind, hash }), { replace: true });
        }
        window.addEventListener("keydown", handleKeyDown);
        return (): void => {
            window.removeEventListener("keydown", handleKeyDown);
        };
    }, [entity, neighbors, navigate]);
}
