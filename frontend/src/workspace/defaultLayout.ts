import type { DockviewApi } from "dockview-react";

import { addRegisteredPanel } from "./addPanel";
import { PANEL_REGISTRY } from "./panelRegistry";

/**
 * The shell's first-run arrangement: Modules, Cloud, and Samples across the top; Module Detail,
 * a Waveform strip, and a tabbed Sample Detail/Stats group underneath each column in turn --
 * driven entirely by each panel's own `placement` in `PANEL_REGISTRY`, so this never has its own,
 * separate idea of where a panel belongs.
 */
export function buildDefaultLayout(api: DockviewApi): void {
    for (const definition of Object.values(PANEL_REGISTRY)) {
        addRegisteredPanel(api, definition);
    }
}
