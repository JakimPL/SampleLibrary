import type { ComponentType } from "react";

import type { ShellView } from "../../navigation/shellView";
import type { IconName } from "../../shared/icons/iconPaths";
import { PANEL_REGISTRY, type PanelDefinition, type PanelId } from "../../workspace/panelRegistry";

/** One of the bottom tabs: a registered panel with an address of its own, in the order the bar shows them. */
export interface PhoneTab {
    readonly id: PanelId;
    readonly title: string;
    readonly shortTitle: string;
    readonly icon: IconName;
    readonly component: ComponentType;
    readonly path: string;
}

/** What a page shows over the tabs: one sample, one module, or a panel with no tab of its own. */
export type PhonePage =
    | { readonly kind: "sample"; readonly sampleHash: string }
    | { readonly kind: "module"; readonly moduleHash: string }
    | { readonly kind: "panel"; readonly panelId: PanelId };

interface OrderedTab {
    readonly tab: PhoneTab;
    readonly order: number;
}

function orderedTabOf(definition: PanelDefinition): OrderedTab | null {
    if (definition.phone.kind !== "tab") {
        return null;
    }
    if (definition.path === null) {
        throw new Error(`the ${definition.id} panel is a phone tab and needs an address of its own`);
    }
    return {
        order: definition.phone.order,
        tab: {
            id: definition.id,
            title: definition.title,
            shortTitle: definition.shortTitle,
            icon: definition.icon,
            component: definition.component,
            path: definition.path,
        },
    };
}

/**
 * The tabs the phone shell offers, in their registered order.
 *
 * Raises `Error` when a panel registered as a tab has no address, since a tab is reached by its
 * address alone.
 */
export function tabPanels(): readonly PhoneTab[] {
    return Object.values(PANEL_REGISTRY)
        .flatMap((definition) => {
            const ordered = orderedTabOf(definition);
            return ordered === null ? [] : [ordered];
        })
        .sort((left, right) => left.order - right.order)
        .map((ordered) => ordered.tab);
}

/** The panels the screen menu lists, each with its address, in their registered order. */
export function overflowPanels(): readonly PhoneTab[] {
    return Object.values(PANEL_REGISTRY).flatMap((definition) =>
        definition.phone.kind === "overflow" && definition.path !== null
            ? [
                  {
                      id: definition.id,
                      title: definition.title,
                      shortTitle: definition.shortTitle,
                      icon: definition.icon,
                      component: definition.component,
                      path: definition.path,
                  },
              ]
            : [],
    );
}

/** The page a view opens over the tabs, or `null` for a view one of the tabs shows. */
export function phonePageOf(view: ShellView): PhonePage | null {
    switch (view.kind) {
        case "sample":
            return { kind: "sample", sampleHash: view.sampleHash };
        case "module":
            return { kind: "module", moduleHash: view.moduleHash };
        case "panel":
            return PANEL_REGISTRY[view.panelId].phone.kind === "tab" ? null : { kind: "panel", panelId: view.panelId };
    }
}

/** The tab a view shows, or `null` for a view a page shows. */
export function tabOf(tabs: readonly PhoneTab[], view: ShellView): PhoneTab | null {
    if (view.kind !== "panel") {
        return null;
    }
    return tabs.find((tab) => tab.id === view.panelId) ?? null;
}

/** The tab at an address, or `null` for an address no tab answers. */
export function tabOfPath(tabs: readonly PhoneTab[], path: string): PhoneTab | null {
    return tabs.find((tab) => tab.path === path) ?? null;
}
