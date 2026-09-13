import type { DockviewApi } from "dockview-react";

import type { PanelId } from "./panelRegistry";

/**
 * Brings a panel to the front of whatever tab group holds it.
 *
 * Panels share a group as readily as they take one of their own -- Sample Detail sits behind Stats
 * in the shell's own first-run arrangement -- so opening an entity is also saying which of a
 * group's panels a person is now looking at. A panel the shell no longer holds is left alone: this
 * says which open panel is in front, and leaves what is open to the person arranging the shell.
 */
export function revealPanel(api: DockviewApi | null, panelId: PanelId): void {
    api?.getPanel(panelId)?.api.setActive();
}
