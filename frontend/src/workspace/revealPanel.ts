import type { DockviewApi } from "dockview-react";

import { addRegisteredPanel } from "./addPanel";
import type { PanelDefinition, PanelId } from "./panelRegistry";

/**
 * Brings a panel to the front of whatever tab group holds it.
 *
 * Panels share a group as readily as they take one of their own -- Sample Detail sits in front of
 * Module Detail and Stats in the shell's own first-run arrangement -- so opening an entity is also
 * saying which of a group's panels a person is now looking at. A panel the shell no longer holds
 * is left alone: this says which open panel is in front, and leaves what is open to the person
 * arranging the shell.
 */
export function revealPanel(api: DockviewApi | null, panelId: PanelId): void {
    api?.getPanel(panelId)?.api.setActive();
}

/**
 * Opens `definition`'s panel at its registered placement when the shell holds none, then brings
 * it forward: what a panel's own address asks for.
 */
export function openAndRevealPanel(api: DockviewApi, definition: PanelDefinition): void {
    if (api.getPanel(definition.id) === undefined) {
        addRegisteredPanel(api, definition);
    }
    api.getPanel(definition.id)?.api.setActive();
}
