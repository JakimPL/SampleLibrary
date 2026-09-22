import { create } from "zustand";

/** How the cloud's points draw: as the scatterplot draws them where the browser can, or as plain dots by the node layer. */
export type CloudDots = "auto" | "plain";

export const CLOUD_DOTS_STORAGE_KEY = "samplelibrary-cloud-dots";
const DEFAULT_CLOUD_DOTS: CloudDots = "auto";

export function isCloudDots(value: string): value is CloudDots {
    return value === "auto" || value === "plain";
}

function readSavedDots(): CloudDots {
    try {
        const raw = localStorage.getItem(CLOUD_DOTS_STORAGE_KEY);
        return raw !== null && isCloudDots(raw) ? raw : DEFAULT_CLOUD_DOTS;
    } catch {
        return DEFAULT_CLOUD_DOTS;
    }
}

function saveDots(dots: CloudDots): void {
    try {
        localStorage.setItem(CLOUD_DOTS_STORAGE_KEY, dots);
    } catch {
        // localStorage throws in private browsing or on a full quota; the choice then lasts for this visit.
    }
}

interface CloudDotsState {
    readonly dots: CloudDots;
}

interface CloudDotsActions {
    readonly setDots: (dots: CloudDots) => void;
}

/** A person's choice of how the cloud's points draw, kept across visits the way the theme is. */
export const useCloudDotsStore = create<CloudDotsState & CloudDotsActions>((set) => ({
    dots: readSavedDots(),
    setDots: (dots) => {
        saveDots(dots);
        set({ dots });
    },
}));
