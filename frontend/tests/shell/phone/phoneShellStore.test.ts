import { describe, expect, it } from "vitest";

import { HOME_TAB_PATH, usePhoneShellStore } from "../../../src/shell/phone/phoneShellStore";

describe("usePhoneShellStore", () => {
    it("starts on the home tab with none shown yet, and the tray closed", () => {
        expect(usePhoneShellStore.getState()).toMatchObject({
            lastTabPath: HOME_TAB_PATH,
            hasShownTab: false,
            trayExpanded: false,
        });
    });

    it("remembers the tab last shown, and that one was", () => {
        usePhoneShellStore.getState().rememberTab("/cloud");

        expect(usePhoneShellStore.getState()).toMatchObject({ lastTabPath: "/cloud", hasShownTab: true });
    });

    it("holds the tray open across the samples it names", () => {
        usePhoneShellStore.getState().setTrayExpanded(true);

        expect(usePhoneShellStore.getState().trayExpanded).toBe(true);
    });
});
