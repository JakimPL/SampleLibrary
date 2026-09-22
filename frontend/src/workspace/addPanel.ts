import type { DockviewApi } from "dockview-react";

import type { PanelDefinition } from "./panelRegistry";

/**
 * Opens one registered panel at its registered placement while that placement's reference panel
 * is open, and wherever dockview puts a panel with no preference otherwise. The View menu, a
 * panel's own address and a saved arrangement gaining a panel all open panels through this one
 * rule, so the three agree on where a panel belongs.
 */
export function addRegisteredPanel(api: DockviewApi, definition: PanelDefinition): void {
    const placement =
        definition.placement !== null && api.panels.some((panel) => panel.id === definition.placement?.referencePanel)
            ? definition.placement
            : null;
    api.addPanel({
        id: definition.id,
        component: definition.id,
        title: definition.title,
        renderer: definition.renderer,
        ...(placement !== null ? { position: placement } : {}),
    });
}
