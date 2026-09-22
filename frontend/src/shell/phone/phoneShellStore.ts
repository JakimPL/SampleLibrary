import { create } from "zustand";

export const HOME_TAB_PATH = "/";

interface PhoneShellState {
    /** The address of the tab last shown, which a page's back button returns to when the visit began on the page. */
    readonly lastTabPath: string;
    /** Whether a tab has been shown in this visit, which is when the history holds one to go back to. */
    readonly hasShownTab: boolean;
}

interface PhoneShellActions {
    readonly rememberTab: (path: string) => void;
}

export const INITIAL_PHONE_SHELL_STATE: PhoneShellState = {
    lastTabPath: HOME_TAB_PATH,
    hasShownTab: false,
};

/** What the phone shell keeps between addresses: where its tabs were. */
export const usePhoneShellStore = create<PhoneShellState & PhoneShellActions>((set) => ({
    ...INITIAL_PHONE_SHELL_STATE,
    rememberTab: (path) => {
        set({ lastTabPath: path, hasShownTab: true });
    },
}));
