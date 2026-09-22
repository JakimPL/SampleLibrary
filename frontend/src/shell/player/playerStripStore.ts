import { create } from "zustand";

export const PLAYER_STRIP_STORAGE_KEY = "samplelibrary-player-strip";

interface PlayerStripState {
    /** Whether the strip shows at all; the View menu switches it. */
    readonly visible: boolean;
    /** Whether the waveform shows beside the transport, or the transport stands alone. */
    readonly expanded: boolean;
}

interface PlayerStripActions {
    readonly setVisible: (visible: boolean) => void;
    readonly toggleExpanded: () => void;
}

const DEFAULT_PLAYER_STRIP_STATE: PlayerStripState = { visible: true, expanded: true };

function isPlayerStripState(value: unknown): value is PlayerStripState {
    if (typeof value !== "object" || value === null) {
        return false;
    }
    const record = value as Record<string, unknown>;
    return typeof record.visible === "boolean" && typeof record.expanded === "boolean";
}

function readSavedState(): PlayerStripState {
    try {
        const raw = localStorage.getItem(PLAYER_STRIP_STORAGE_KEY);
        if (raw === null) {
            return DEFAULT_PLAYER_STRIP_STATE;
        }
        const parsed: unknown = JSON.parse(raw);
        return isPlayerStripState(parsed) ? parsed : DEFAULT_PLAYER_STRIP_STATE;
    } catch {
        return DEFAULT_PLAYER_STRIP_STATE;
    }
}

function saveState(state: PlayerStripState): void {
    try {
        localStorage.setItem(PLAYER_STRIP_STORAGE_KEY, JSON.stringify(state));
    } catch {
        // localStorage throws in private browsing or on a full quota; the choice then lasts for this session.
    }
}

/** How the player strip stands, kept across visits the way the theme is. */
export const usePlayerStripStore = create<PlayerStripState & PlayerStripActions>((set, get) => ({
    ...readSavedState(),
    setVisible: (visible) => {
        const next = { visible, expanded: get().expanded };
        saveState(next);
        set(next);
    },
    toggleExpanded: () => {
        const next = { visible: get().visible, expanded: !get().expanded };
        saveState(next);
        set(next);
    },
}));
