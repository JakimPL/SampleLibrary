import { useEffect } from "react";

import { useSelectionStore } from "../workspace/selectionStore";
import type { ShellView } from "./shellView";

/**
 * Focuses the entity an address names, so a pasted link, a double-click and a page's own button
 * all reach the detail through the one mechanism: the address changes, and this effect follows it.
 */
export function useRouteFocus(view: ShellView): void {
    const focusSample = useSelectionStore((state) => state.focusSample);
    const focusModule = useSelectionStore((state) => state.focusModule);

    useEffect(() => {
        switch (view.kind) {
            case "sample":
                focusSample(view.sampleHash);
                break;
            case "module":
                focusModule(view.moduleHash);
                break;
            case "panel":
                break;
        }
    }, [view, focusSample, focusModule]);
}
