import type { DockviewApi } from "dockview-react";

import { PANEL_REGISTRY } from "./panelRegistry";

/**
 * The shell's first-run arrangement: Modules, Cloud, and Samples across the top; Module Detail,
 * a Waveform strip, and a tabbed Sample Detail/Stats group underneath each column in turn.
 */
export function buildDefaultLayout(api: DockviewApi): void {
    const modulesList = PANEL_REGISTRY["modules-list"];
    const cloud = PANEL_REGISTRY.cloud;
    const samplesList = PANEL_REGISTRY["samples-list"];
    const waveform = PANEL_REGISTRY.waveform;
    const moduleDetail = PANEL_REGISTRY["module-detail"];
    const sampleDetail = PANEL_REGISTRY["sample-detail"];
    const stats = PANEL_REGISTRY.stats;

    api.addPanel({ id: modulesList.id, component: modulesList.id, title: modulesList.title });
    api.addPanel({
        id: cloud.id,
        component: cloud.id,
        title: cloud.title,
        position: { direction: "right", referencePanel: modulesList.id },
    });
    api.addPanel({
        id: samplesList.id,
        component: samplesList.id,
        title: samplesList.title,
        position: { direction: "right", referencePanel: cloud.id },
    });
    api.addPanel({
        id: waveform.id,
        component: waveform.id,
        title: waveform.title,
        position: { direction: "below", referencePanel: cloud.id },
    });
    api.addPanel({
        id: moduleDetail.id,
        component: moduleDetail.id,
        title: moduleDetail.title,
        position: { direction: "below", referencePanel: modulesList.id },
    });
    api.addPanel({
        id: sampleDetail.id,
        component: sampleDetail.id,
        title: sampleDetail.title,
        position: { direction: "below", referencePanel: samplesList.id },
    });
    api.addPanel({
        id: stats.id,
        component: stats.id,
        title: stats.title,
        position: { direction: "within", referencePanel: sampleDetail.id },
    });
}
