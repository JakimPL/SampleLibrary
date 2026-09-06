import type { MouseEvent } from "react";
import { useNavigate } from "react-router-dom";

import { type EntityRef, useSelectionStore } from "./selectionStore";
import { useIsHighlighted } from "./useIsHighlighted";

const ENTITY_ROUTE_PREFIX: Record<EntityRef["kind"], string> = {
    sample: "/samples/",
    module: "/modules/",
};

export interface EntityRowInteractions {
    readonly href: string;
    readonly isHighlighted: boolean;
    readonly isFocused: boolean;
    readonly onClick: (event: MouseEvent) => void;
    readonly onDoubleClick: (event: MouseEvent) => void;
}

export function entityRoute(entity: EntityRef): string {
    return `${ENTITY_ROUTE_PREFIX[entity.kind]}${entity.hash}`;
}

/**
 * Wires the shell's click-to-highlight / double-click-to-focus convention for one row or point.
 *
 * A plain, unmodified click only highlights `entity`, staying on the current view; a Shift-click
 * on a sample instead sets it as the comparison target read by `SpectralDistanceReadout`, leaving
 * the highlight untouched -- a Shift-click on a module has no comparison concept to set, so it is
 * left alone. Any other modified click (ctrl/cmd/alt, or a non-primary button) is left alone too,
 * so a row's own link can still open in a new tab as usual. A double-click navigates to `entity`'s
 * own route, which is what actually focuses it -- the shell's route-param effect is the one place
 * that dispatches a focus action, so a pasted URL and a double-click both focus an entity through
 * the identical mechanism.
 */
export function useEntityRowInteractions(entity: EntityRef): EntityRowInteractions {
    const navigate = useNavigate();
    const isHighlighted = useIsHighlighted(entity);
    const isFocused = useSelectionStore((state) =>
        entity.kind === "sample" ? state.focusedSampleHash === entity.hash : state.focusedModuleHash === entity.hash,
    );
    const highlightEntity = useSelectionStore((state) => state.highlightEntity);
    const setComparisonSample = useSelectionStore((state) => state.setComparisonSample);

    function onClick(event: MouseEvent): void {
        if (event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey) {
            return;
        }
        if (event.shiftKey) {
            if (entity.kind === "sample") {
                event.preventDefault();
                setComparisonSample(entity.hash);
            }
            return;
        }
        event.preventDefault();
        highlightEntity(entity);
    }

    function onDoubleClick(event: MouseEvent): void {
        event.preventDefault();
        void navigate(entityRoute(entity));
    }

    return { href: entityRoute(entity), isHighlighted, isFocused, onClick, onDoubleClick };
}
