import type { ComponentType } from "react";

import type { IconName } from "../shared/icons/iconPaths";
import { CloudPanel } from "./panels/CloudPanel";
import { ModuleDetailPanel } from "./panels/ModuleDetailPanel";
import { ModulesListPanel } from "./panels/ModulesListPanel";
import { MorphPanel } from "./panels/MorphPanel";
import { SampleDetailPanel } from "./panels/SampleDetailPanel";
import { SamplesListPanel } from "./panels/SamplesListPanel";
import { StatsPanel } from "./panels/StatsPanel";

export type PanelId = "samples-list" | "modules-list" | "cloud" | "morph" | "sample-detail" | "module-detail" | "stats";

export interface PanelPlacement {
    readonly direction: "right" | "below" | "within";
    readonly referencePanel: PanelId;
}

/** How dockview keeps a panel tabbed away: `always` leaves its DOM in place, so a drawn WebGL scene survives. */
export type PanelRenderer = "onlyWhenVisible" | "always";

/** Where a panel lives on a phone: a bottom tab, a page pushed over the tabs, or a screen menu's overflow. */
export type PhoneHome =
    { readonly kind: "tab"; readonly order: number } | { readonly kind: "page" } | { readonly kind: "overflow" };

export interface PanelDefinition {
    readonly id: PanelId;
    readonly title: string;
    readonly shortTitle: string;
    readonly icon: IconName;
    readonly component: ComponentType;
    /**
     * Where the panel reopens beside an open one, shared by the View menu and a saved arrangement
     * gaining a panel; `null` for `samples-list`, which anchors every arrangement.
     */
    readonly placement: PanelPlacement | null;
    readonly renderer: PanelRenderer;
    /** The address that shows the panel, or `null` for a panel an entity's own address reveals. */
    readonly path: string | null;
    readonly phone: PhoneHome;
}

/**
 * Every panel the shells can mount, by id. Adding a new panel is one new entry here plus its own
 * presentational and container components, and a place in `defaultLayout.ts`. Declared in an
 * order where a panel's own `placement.referencePanel` always already precedes it, since a saved
 * arrangement gains panels in this same order.
 */
export const PANEL_REGISTRY: Readonly<Record<PanelId, PanelDefinition>> = {
    "samples-list": {
        id: "samples-list",
        title: "Samples",
        shortTitle: "Samples",
        icon: "samples",
        component: SamplesListPanel,
        placement: null,
        renderer: "onlyWhenVisible",
        path: "/",
        phone: { kind: "tab", order: 1 },
    },
    "modules-list": {
        id: "modules-list",
        title: "Modules",
        shortTitle: "Modules",
        icon: "modules",
        component: ModulesListPanel,
        placement: { direction: "within", referencePanel: "samples-list" },
        renderer: "onlyWhenVisible",
        path: "/modules",
        phone: { kind: "tab", order: 3 },
    },
    cloud: {
        id: "cloud",
        title: "Cloud",
        shortTitle: "Cloud",
        icon: "cloud",
        component: CloudPanel,
        placement: { direction: "right", referencePanel: "samples-list" },
        renderer: "always",
        path: "/cloud",
        phone: { kind: "tab", order: 2 },
    },
    "sample-detail": {
        id: "sample-detail",
        title: "Sample Detail",
        shortTitle: "Sample",
        icon: "detail",
        component: SampleDetailPanel,
        placement: { direction: "right", referencePanel: "cloud" },
        renderer: "onlyWhenVisible",
        path: null,
        phone: { kind: "page" },
    },
    "module-detail": {
        id: "module-detail",
        title: "Module Detail",
        shortTitle: "Module",
        icon: "detail",
        component: ModuleDetailPanel,
        placement: { direction: "within", referencePanel: "sample-detail" },
        renderer: "onlyWhenVisible",
        path: null,
        phone: { kind: "page" },
    },
    morph: {
        id: "morph",
        title: "Morph",
        shortTitle: "Morph",
        icon: "morph",
        component: MorphPanel,
        placement: { direction: "within", referencePanel: "sample-detail" },
        renderer: "onlyWhenVisible",
        path: "/morph",
        phone: { kind: "tab", order: 4 },
    },
    stats: {
        id: "stats",
        title: "Stats",
        shortTitle: "Stats",
        icon: "stats",
        component: StatsPanel,
        placement: { direction: "within", referencePanel: "sample-detail" },
        renderer: "onlyWhenVisible",
        path: "/stats",
        phone: { kind: "overflow" },
    },
};
