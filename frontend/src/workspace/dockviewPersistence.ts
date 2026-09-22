import type { DockviewApi, SerializedDockview } from "dockview-react";

import { addRegisteredPanel } from "./addPanel";
import { buildDefaultLayout } from "./defaultLayout";
import { PANEL_REGISTRY } from "./panelRegistry";

export const LAYOUT_VERSION = 2;
export const LAYOUT_STORAGE_KEY = "samplelibrary-workspace-layout";
/** Held the registry's panel ids beside the arrangement before the record carried them itself. */
const RETIRED_KNOWN_PANELS_STORAGE_KEY = "samplelibrary-workspace-panels";

export interface StoredLayout {
    readonly version: number;
    readonly layout: SerializedDockview;
    /** The panels the registry held when the arrangement was saved. */
    readonly knownPanels: readonly string[];
}

function isStoredLayout(value: unknown): value is StoredLayout {
    if (typeof value !== "object" || value === null) {
        return false;
    }
    const record = value as Record<string, unknown>;
    return (
        record.version === LAYOUT_VERSION &&
        typeof record.layout === "object" &&
        record.layout !== null &&
        Array.isArray(record.knownPanels) &&
        record.knownPanels.every((id) => typeof id === "string")
    );
}

/** The saved record of this version, or `null` for none, an unreadable one, or one of another version. */
function readStoredLayout(): StoredLayout | null {
    try {
        const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
        if (raw === null) {
            return null;
        }
        const parsed: unknown = JSON.parse(raw);
        return isStoredLayout(parsed) ? parsed : null;
    } catch {
        return null;
    }
}

function discardStoredLayout(): void {
    try {
        localStorage.removeItem(LAYOUT_STORAGE_KEY);
        localStorage.removeItem(RETIRED_KNOWN_PANELS_STORAGE_KEY);
    } catch {
        // localStorage throws in private browsing or on a full quota; nothing was kept there anyway.
    }
}

function saveWorkspace(api: DockviewApi): void {
    const record: StoredLayout = {
        version: LAYOUT_VERSION,
        layout: api.toJSON(),
        knownPanels: Object.keys(PANEL_REGISTRY),
    };
    try {
        localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(record));
    } catch {
        // localStorage throws in private browsing or on a full quota; the layout then lasts for this session.
    }
}

function restoreSavedLayout(api: DockviewApi, layout: SerializedDockview): boolean {
    try {
        api.fromJSON(layout);
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
 * Restores the last saved arrangement of this record version, completed with any panel registered
 * since it was saved, and otherwise discards whatever was kept and draws the first-run
 * arrangement; then keeps saving every subsequent layout change -- resizing, rearranging, or
 * adding a panel. A record of another version is what an older build saved, and the current
 * arrangement takes its place.
 */
export function restoreOrBuildLayout(api: DockviewApi): void {
    const stored = readStoredLayout();
    if (stored !== null && restoreSavedLayout(api, stored.layout)) {
        if (addPanelsRegisteredSince(api, new Set(stored.knownPanels))) {
            saveWorkspace(api);
        }
    } else {
        discardStoredLayout();
        buildDefaultLayout(api);
    }

    api.onDidLayoutChange(() => {
        saveWorkspace(api);
    });
}

/** Discards whatever arrangement got saved, however it got scrambled, and draws the first-run one again. */
export function resetLayout(api: DockviewApi): void {
    discardStoredLayout();
    buildDefaultLayout(api);
}
