import type { ReactElement } from "react";
import { useState } from "react";

import { withBoundary } from "../../shared/ErrorBoundary";
import { PanelHost } from "../../shared/panel/PanelHost";
import type { PanelId } from "../../workspace/panelRegistry";
import type { PhoneTab } from "./phoneView";

interface PhoneSurfacesProps {
    readonly tabs: readonly PhoneTab[];
    /** The tab in front, or `null` while a page covers them all. */
    readonly activeTabId: PanelId | null;
}

/**
 * The tabs' panels, each mounted on its first visit and kept mounted from then on: a tab that is
 * out of sight keeps its scroll position, its filters, the rows it loaded and its drawn cloud,
 * hidden from sight and from the focus order until it is back in front.
 */
export function PhoneSurfaces({ tabs, activeTabId }: PhoneSurfacesProps): ReactElement {
    const [visited, setVisited] = useState<ReadonlySet<PanelId>>(
        () => new Set(activeTabId === null ? [] : [activeTabId]),
    );
    if (activeTabId !== null && !visited.has(activeTabId)) {
        setVisited(new Set([...visited, activeTabId]));
    }

    return (
        <div className="phone-surfaces">
            {tabs
                .filter((tab) => visited.has(tab.id))
                .map((tab) => {
                    const Surface = tab.component;
                    const active = tab.id === activeTabId;
                    return (
                        <section
                            key={tab.id}
                            className="phone-surface"
                            aria-label={tab.title}
                            data-active={active}
                            aria-hidden={!active}
                            inert={!active}
                        >
                            {withBoundary(
                                <PanelHost panelId={tab.id}>
                                    <Surface />
                                </PanelHost>,
                            )}
                        </section>
                    );
                })}
        </div>
    );
}
