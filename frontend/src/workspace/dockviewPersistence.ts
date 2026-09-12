import type { DockviewApi } from "dockview-react";

import { addRegisteredPanel } from "./addPanel";
import { buildDefaultLayout } from "./defaultLayout";
import { PANEL_REGISTRY } from "./panelRegistry";

export const LAYOUT_STORAGE_KEY = "samplelibrary-workspace-layout";
export const KNOWN_PANELS_STORAGE_KEY = "samplelibrary-workspace-panels";

function readStored(key: string): unknown {
    try {
        const raw = localStorage.getItem(key);
        return raw === null ? null : (JSON.parse(raw) as unknown);
    } catch {
        return null;
    }
}

/** The panels the registry held when the arrangement was saved; an arrangement saved before this was recorded knows none. */
function readKnownPanelIds(): ReadonlySet<string> {
    const stored = readStored(KNOWN_PANELS_STORAGE_KEY);
    return new Set(Array.isArray(stored) ? stored.filter((id): id is string => typeof id === "string") : []);
}

function saveWorkspace(api: DockviewApi): void {
    try {
        localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(api.toJSON()));
        localStorage.setItem(KNOWN_PANELS_STORAGE_KEY, JSON.stringify(Object.keys(PANEL_REGISTRY)));
    } catch {
        // localStorage can be unavailable (private browsing, a full quota) -- losing layout
        // persistence for this session is an acceptable degradation, not a reason to crash the shell.
    }
}

function restoreSavedLayout(api: DockviewApi, saved: unknown): boolean {
    try {
        api.fromJSON(saved as Parameters<DockviewApi["fromJSON"]>[0]);
        return true;
    } catch {
        return false;
    }
}

/**
 * Opens every panel registered after the arrangement was saved, so a panel the shell gains shows
 * up for a person who arranged the shell before it existed, while a panel they closed themselves
 * stays closed. Reports whether any was opened.
 */
function addPanelsRegisteredSince(api: DockviewApi, knownPanelIds: ReadonlySet<string>): boolean {
    let added = false;
    for (const definition of Object.values(PANEL_REGISTRY)) {
        if (!knownPanelIds.has(definition.id) && api.getPanel(definition.id) === undefined) {
            addRegisteredPanel(api, definition);
            added = true;
        }
    }
    return added;
}

/**
 * Restores the shell's last saved panel arrangement, completed with any panel registered since it
 * was saved, or builds the default one on first run, then keeps saving every subsequent layout
 * change -- resizing, rearranging, or adding a panel.
 */
export function restoreOrBuildLayout(api: DockviewApi): void {
    const saved = readStored(LAYOUT_STORAGE_KEY);
    if (saved !== null && restoreSavedLayout(api, saved)) {
        if (addPanelsRegisteredSince(api, readKnownPanelIds())) {
            saveWorkspace(api);
        }
    } else {
        buildDefaultLayout(api);
    }

    api.onDidLayoutChange(() => {
        saveWorkspace(api);
    });
}

/**
 * Discards whatever arrangement got saved -- however it got scrambled -- and rebuilds the shell's
 * first-run default in its place.
 */
export function resetLayout(api: DockviewApi): void {
    try {
        localStorage.removeItem(LAYOUT_STORAGE_KEY);
        localStorage.removeItem(KNOWN_PANELS_STORAGE_KEY);
    } catch {
        // localStorage can be unavailable (private browsing, a full quota) -- the in-memory rebuild
        // below still succeeds even though this run won't remember it past a reload.
    }

    for (const panel of [...api.panels]) {
        api.removePanel(panel);
    }
    buildDefaultLayout(api);
}
