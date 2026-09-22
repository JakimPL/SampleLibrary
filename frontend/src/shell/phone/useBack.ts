import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { usePhoneShellStore } from "./phoneShellStore";

/**
 * Where a page's back button goes: one step back through the history once a tab has been shown in
 * this visit, and to the tab last remembered when the visit began on the page itself, so a link
 * opened cold still has a list to return to.
 */
export function useBack(): () => void {
    const navigate = useNavigate();
    const hasShownTab = usePhoneShellStore((state) => state.hasShownTab);
    const lastTabPath = usePhoneShellStore((state) => state.lastTabPath);

    return useCallback((): void => {
        if (hasShownTab) {
            void navigate(-1);
        } else {
            void navigate(lastTabPath, { replace: true });
        }
    }, [hasShownTab, lastTabPath, navigate]);
}
