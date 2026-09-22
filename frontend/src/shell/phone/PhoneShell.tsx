import type { ReactElement } from "react";
import { useEffect, useMemo } from "react";

import { useLayoutMode } from "../../layout/useLayoutMode";
import type { ShellView } from "../../navigation/shellView";
import { hintFor } from "../../shared/hints";
import type { PanelId } from "../../workspace/panelRegistry";
import { PageBody, PageHeaderFor } from "./PageLayer";
import { usePhoneShellStore } from "./phoneShellStore";
import { PhoneSurfaces } from "./PhoneSurfaces";
import { phonePageOf, type PhoneTab, tabOf, tabOfPath, tabPanels } from "./phoneView";
import { ScreenMenu } from "./ScreenMenu";
import { TabBar } from "./TabBar";
import { Tray } from "./Tray";

/**
 * The tab the shell stands on for a view: the view's own tab, else the tab last shown, else the
 * first registered one, which is where a visit that began on a page returns to.
 */
function standingTab(tabs: readonly PhoneTab[], view: ShellView, lastTabPath: string): PhoneTab {
    const tab = tabOf(tabs, view) ?? tabOfPath(tabs, lastTabPath) ?? tabs[0];
    if (tab === undefined) {
        throw new Error("the registry names no panel as a phone tab");
    }
    return tab;
}

interface PhoneShellProps {
    readonly view: ShellView;
}

/** The tab whose tray slot stays, with the gestures spelled out, while nothing is in hand. */
const CLOUD_TAB_ID: PanelId = "cloud";

/**
 * The shell a phone gets: one header, one surface at a time over the tabs' panels, the tray naming
 * what is in hand, and the tab bar along the bottom. A sample, a module or a panel with no tab
 * opens as a page in the same frame, taking the header for its own name and steps and covering the
 * tray, whose controls the page carries itself.
 */
export function PhoneShell({ view }: PhoneShellProps): ReactElement {
    const tabs = useMemo(tabPanels, []);
    const lastTabPath = usePhoneShellStore((state) => state.lastTabPath);
    const rememberTab = usePhoneShellStore((state) => state.rememberTab);
    const { input } = useLayoutMode();
    const page = phonePageOf(view);
    const viewTab = tabOf(tabs, view);
    const tab = standingTab(tabs, view, lastTabPath);

    useEffect(() => {
        if (viewTab !== null) {
            rememberTab(viewTab.path);
        }
    }, [viewTab, rememberTab]);

    return (
        <div className="phone-shell">
            <header className="phone-header">
                {page === null ? (
                    <>
                        <h1 className="phone-header-title">{tab.title}</h1>
                        <ScreenMenu />
                    </>
                ) : (
                    <PageHeaderFor page={page} />
                )}
            </header>
            <div className="phone-main">
                <PhoneSurfaces tabs={tabs} activeTabId={page === null ? tab.id : null} />
                {page !== null && (
                    <div className="phone-page">
                        <PageBody page={page} />
                    </div>
                )}
            </div>
            {page === null && <Tray idleHint={tab.id === CLOUD_TAB_ID ? hintFor("cloudIdle", input) : null} />}
            <TabBar tabs={tabs} activeTabId={tab.id} />
        </div>
    );
}
