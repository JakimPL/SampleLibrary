import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { useMorphStore } from "../../morph/morphStore";
import { classNames } from "../../shared/classNames";
import { Icon } from "../../shared/icons/Icon";
import type { PanelId } from "../../workspace/panelRegistry";
import type { PhoneTab } from "./phoneView";

const CLOUD_TAB_ID: PanelId = "cloud";

/** How far the morph pair has come: nothing chosen, one end chosen, or both. */
export type PairState = "none" | "half" | "full";

export function pairStateOf(first: string | null, second: string | null): PairState {
    if (first !== null && second !== null) {
        return "full";
    }
    return first !== null || second !== null ? "half" : "none";
}

interface TabBarProps {
    readonly tabs: readonly PhoneTab[];
    readonly activeTabId: PanelId | null;
}

/**
 * The bar of tabs along the bottom edge. Each tab replaces the address rather than adding to the
 * history, so the back button always leaves a page for the tab it came from. The Cloud tab, where
 * the morph lives, carries a dot while a pair is being built: hollow with one end chosen, filled
 * once both are.
 */
export function TabBar({ tabs, activeTabId }: TabBarProps): ReactElement {
    const first = useMorphStore((state) => state.first);
    const second = useMorphStore((state) => state.second);
    const pairState = pairStateOf(first, second);

    return (
        <nav className="tab-bar" aria-label="Sections">
            {tabs.map((tab) => (
                <Link
                    key={tab.id}
                    to={tab.path}
                    replace
                    className="tab-bar-link"
                    aria-current={tab.id === activeTabId ? "page" : undefined}
                >
                    <Icon name={tab.icon} label={null} />
                    <span className="tab-bar-label">{tab.shortTitle}</span>
                    {tab.id === CLOUD_TAB_ID && pairState !== "none" && (
                        <span
                            className={classNames("tab-bar-dot", pairState === "half" && "is-half")}
                            data-testid="morph-pair-dot"
                            aria-hidden
                        />
                    )}
                </Link>
            ))}
        </nav>
    );
}
