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

export interface PanelDefinition {
    readonly id: PanelId;
    readonly title: string;
    readonly component: ComponentType;
}

/**
 * Every panel the shell can mount, by id. Adding a new panel is one new entry here plus its own
 * presentational and container components -- nothing else in the shell needs to change.
 */
export const PANEL_REGISTRY: Readonly<Record<PanelId, PanelDefinition>> = {
    "modules-list": { id: "modules-list", title: "Modules", component: ModulesListPanel },
    "samples-list": { id: "samples-list", title: "Samples", component: SamplesListPanel },
    cloud: { id: "cloud", title: "Cloud", component: CloudPanel },
    waveform: { id: "waveform", title: "Waveform", component: WaveformPanel },
    "module-detail": { id: "module-detail", title: "Module Detail", component: ModuleDetailPanel },
    "sample-detail": { id: "sample-detail", title: "Sample Detail", component: SampleDetailPanel },
    stats: { id: "stats", title: "Stats", component: StatsPanel },
};
