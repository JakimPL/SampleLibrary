import type { components } from "../api/schema";

export type SampleCategory = components["schemas"]["SampleCategory"];

// Each category's index into the cloud's palette; every entry has a `--category-*` property in styles.css.
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
    // Custom properties are kebab-case under stylelint; the categories mirror the backend's snake_case enum.
    return `--category-${category.replace(/_/g, "-")}`;
}

export function categoryIndex(category: SampleCategory): number {
    return CATEGORY_ORDER.indexOf(category);
}
