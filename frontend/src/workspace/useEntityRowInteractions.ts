import type { KeyboardEvent, MouseEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useMorphStore } from "../morph/morphStore";
import { KEYBOARD_CLICK_DETAIL } from "../shared/gestures/gestureThresholds";
import { ROW_LINK_ATTRIBUTE } from "./rowLinks";
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
    readonly onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
}

export function entityRoute(entity: EntityRef): string {
    return `${ENTITY_ROUTE_PREFIX[entity.kind]}${entity.hash}`;
}

function isRowLink(target: EventTarget | null): boolean {
    return target instanceof Element && target.closest(`[${ROW_LINK_ATTRIBUTE}]`) !== null;
}

/** Moves the focus to the same link in the row before or after the one holding it. */
function focusSiblingRowLink(element: HTMLElement, direction: "previous" | "next"): void {
    const row = element.closest("tr");
    const sibling = direction === "next" ? row?.nextElementSibling : row?.previousElementSibling;
    sibling?.querySelector<HTMLElement>("a[href]")?.focus();
}

/**
 * Wires the shell's click-to-highlight / double-click-to-focus convention for one row or point.
 *
 * A plain, unmodified click highlights `entity`, staying on the current view, and gives a sample to
 * the morph's selected end. A modified click (shift/ctrl/cmd/alt, or a non-primary button) is left
 * to the browser, so a row's own link opens in a new tab or window as usual. A double-click
 * navigates to `entity`'s own route, which is what actually focuses it -- the shell's route effect
 * is the one place that dispatches a focus action, so a pasted URL and a double-click both focus an
 * entity through the identical mechanism. Two clicks reach the route the same way: one a key press raised on the
 * row's link, which Enter is, and one on a control marked as a row link, which opens the entity or
 * leaves the app for the page it came from.
 *
 * The arrow keys on the link move the focus down or up the rows.
 *
 * `onClick` must be attached as `onClickCapture` on the row, not `onClick`: every row wraps its
 * name in its own `<Link>`, and a bubble-phase handler on the row runs only after that inner
 * `<Link>`'s own bubble-phase handler already read `event.defaultPrevented` and navigated -- by
 * then, calling `preventDefault` here is too late to stop it. Running in the capture phase puts
 * this handler ahead of the `<Link>` on the event path, so a plain click's `preventDefault` lands
 * before the `<Link>` ever sees the event, leaving navigation to the double-click handler alone as
 * intended. Skipping this would fire an unintended navigation (and the focus it triggers) on every
 * plain click, alongside the highlight this hook already dispatches for it.
 */
export function useEntityRowInteractions(entity: EntityRef): EntityRowInteractions {
    const navigate = useNavigate();
    const isHighlighted = useIsHighlighted(entity);
    const isFocused = useSelectionStore((state) =>
        entity.kind === "sample" ? state.focusedSampleHash === entity.hash : state.focusedModuleHash === entity.hash,
    );
    const highlightEntity = useSelectionStore((state) => state.highlightEntity);
    const takeSample = useMorphStore((state) => state.takeSample);

    function onClick(event: MouseEvent): void {
        if (event.button !== 0 || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) {
            return;
        }
        if (event.detail === KEYBOARD_CLICK_DETAIL || isRowLink(event.target)) {
            return;
        }
        event.preventDefault();
        highlightEntity(entity);
        if (entity.kind === "sample") {
            takeSample(entity.hash);
        }
    }

    function onDoubleClick(event: MouseEvent): void {
        event.preventDefault();
        void navigate(entityRoute(entity));
    }

    function onKeyDown(event: KeyboardEvent<HTMLElement>): void {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            focusSiblingRowLink(event.currentTarget, event.key === "ArrowDown" ? "next" : "previous");
        }
    }

    return { href: entityRoute(entity), isHighlighted, isFocused, onClick, onDoubleClick, onKeyDown };
}
