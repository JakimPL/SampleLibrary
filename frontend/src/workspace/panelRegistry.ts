import type { ComponentType } from "react";

import { CloudPanel } from "./panels/CloudPanel";
import { ModuleDetailPanel } from "./panels/ModuleDetailPanel";
import { ModulesListPanel } from "./panels/ModulesListPanel";
import { SampleDetailPanel } from "./panels/SampleDetailPanel";
import { SamplesListPanel } from "./panels/SamplesListPanel";
import { StatsPanel } from "./panels/StatsPanel";
import { WaveformPanel } from "./panels/WaveformPanel";

export type PanelId =
    "modules-list" | "samples-list" | "cloud" | "waveform" | "module-detail" | "sample-detail" | "stats";

export interface PanelPlacement {
    readonly direction: "right" | "below" | "within";
    readonly referencePanel: PanelId;
}

export interface PanelDefinition {
    readonly id: PanelId;
    readonly title: string;
    readonly component: ComponentType;
    // Where this panel belongs relative to another already-open one. `buildDefaultLayout` and
    // `AddPanelMenu` (re-adding a panel closed via its own tab) both place a panel this same way,
    // so the two can never drift apart into disagreeing about where a panel belongs -- `null` for
    // `modules-list`, the one panel every layout anchors around instead of positioning relative to.
    readonly placement: PanelPlacement | null;
}

/**
 * Every panel the shell can mount, by id. Adding a new panel is one new entry here plus its own
 * presentational and container components -- nothing else in the shell needs to change. Declared
 * in an order where a panel's own `placement.referencePanel` always already precedes it, since
 * `buildDefaultLayout` adds them in this same order.
 */
export const PANEL_REGISTRY: Readonly<Record<PanelId, PanelDefinition>> = {
    "modules-list": { id: "modules-list", title: "Modules", component: ModulesListPanel, placement: null },
    cloud: {
        id: "cloud",
        title: "Cloud",
        component: CloudPanel,
        placement: { direction: "right", referencePanel: "modules-list" },
    },
    "samples-list": {
        id: "samples-list",
        title: "Samples",
        component: SamplesListPanel,
        placement: { direction: "right", referencePanel: "cloud" },
    },
    waveform: {
        id: "waveform",
        title: "Waveform",
        component: WaveformPanel,
        placement: { direction: "below", referencePanel: "cloud" },
    },
    "module-detail": {
        id: "module-detail",
        title: "Module Detail",
        component: ModuleDetailPanel,
        placement: { direction: "below", referencePanel: "modules-list" },
    },
    "sample-detail": {
        id: "sample-detail",
        title: "Sample Detail",
        component: SampleDetailPanel,
        placement: { direction: "below", referencePanel: "samples-list" },
    },
    stats: {
        id: "stats",
        title: "Stats",
        component: StatsPanel,
        placement: { direction: "within", referencePanel: "sample-detail" },
    },
};
