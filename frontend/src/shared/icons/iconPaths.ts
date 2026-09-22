export type IconName = "samples" | "cloud" | "modules" | "waveform" | "morph" | "detail" | "stats";

/** Stroke paths on a 24-unit grid, drawn by `Icon` with a round two-unit stroke. */
export const ICON_PATHS: Readonly<Record<IconName, string>> = {
    samples: "M4 6h16M4 12h10M4 18h13",
    cloud: "M6 8h.01M12 5h.01M17 9h.01M9 14h.01M15 16h.01M5 18h.01M19 17h.01",
    modules: "M9 18V6l10-2v12M9 18a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0M19 16a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0",
    waveform: "M3 12h2l2-6 3 12 3-9 2 6 2-3h4",
    morph: "M10 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0M20 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0M10 12h4",
    detail: "M12 8h.01M11 12h1v4h1M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    stats: "M5 20v-9M12 20V4M19 20v-6",
};
