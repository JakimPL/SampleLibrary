import type { DockviewApi } from "dockview-react";

import { buildDefaultLayout } from "./defaultLayout";

const STORAGE_KEY = "samplelibrary-workspace-layout";

function readSavedLayout(): unknown {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw === null ? null : (JSON.parse(raw) as unknown);
    } catch {
        return null;
    }
}

function saveLayout(api: DockviewApi): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(api.toJSON()));
    } catch {
        // localStorage can be unavailable (private browsing, a full quota) -- losing layout
        // persistence for this session is an acceptable degradation, not a reason to crash the shell.
    }
}

/**
 * Restores the shell's last saved panel arrangement, or builds the default one on first run, then
 * keeps saving every subsequent layout change -- resizing, rearranging, or adding a panel.
 */
export function restoreOrBuildLayout(api: DockviewApi): void {
    const saved = readSavedLayout();
    if (saved === null) {
        buildDefaultLayout(api);
    } else {
        try {
            api.fromJSON(saved as Parameters<DockviewApi["fromJSON"]>[0]);
        } catch {
            buildDefaultLayout(api);
        }
    }

    api.onDidLayoutChange(() => {
        saveLayout(api);
    });
}

/**
 * Discards whatever arrangement got saved -- however it got scrambled -- and rebuilds the shell's
 * first-run default in its place.
 */
export function resetLayout(api: DockviewApi): void {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch {
        // localStorage can be unavailable (private browsing, a full quota) -- the in-memory rebuild
        // below still succeeds even though this run won't remember it past a reload.
    }

    for (const panel of [...api.panels]) {
        api.removePanel(panel);
    }
    buildDefaultLayout(api);
}
