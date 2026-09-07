import type { components } from "../api/schema";

export type SampleCategory = components["schemas"]["SampleCategory"];

// Fixed draw order for the cloud's categorical coloring (each category's index into the palette
// CloudView.tsx builds) and the order a legend would list them in -- mirrors the CSS custom
// property names declared per SampleCategory in styles.css (--category-kick, --category-snare, …).
export const CATEGORY_ORDER: readonly SampleCategory[] = [
    "kick",
    "snare",
    "clap",
    "hi_hat",
    "cymbal",
    "percussion",
    "bass",
    "lead",
    "pad",
    "pluck",
    "vocal",
    "fx",
    "loop",
    "uncategorized",
];

export const CATEGORY_LABELS: Readonly<Record<SampleCategory, string>> = {
    kick: "Kick",
    snare: "Snare",
    clap: "Clap",
    hi_hat: "Hi-Hat",
    cymbal: "Cymbal",
    percussion: "Percussion",
    bass: "Bass",
    lead: "Lead",
    pad: "Pad",
    pluck: "Pluck",
    vocal: "Vocal",
    fx: "FX",
    loop: "Loop",
    uncategorized: "Uncategorized",
};

export function categoryColorProperty(category: SampleCategory): string {
    // CSS custom property names are kebab-case by convention (enforced by stylelint), while
    // SampleCategory's own values mirror the backend enum verbatim, snake_case included.
    return `--category-${category.replace(/_/g, "-")}`;
}

export function categoryIndex(category: SampleCategory): number {
    return CATEGORY_ORDER.indexOf(category);
}
