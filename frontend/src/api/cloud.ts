import { requestJson } from "./client";
import type { TagSummary } from "./curation";
import type { components } from "./schema";

export type CloudPoint = components["schemas"]["SampleCloudPoint"];
export type ModuleCloudPoint = components["schemas"]["ModuleCloudPoint"];
/** What a person decided one sample is: its tag paths, in the order they wrote them. */
export type CloudLabel = components["schemas"]["CloudLabel"];
/** What the listening model hears one sample as: its category as a tag path, with the score behind it. */
export type CloudCategory = components["schemas"]["CloudSuggestion"];

export async function getCloud(): Promise<readonly CloudPoint[]> {
    return requestJson<readonly CloudPoint[]>("/cloud");
}

export async function getModuleCloud(): Promise<readonly ModuleCloudPoint[]> {
    return requestJson<readonly ModuleCloudPoint[]>("/cloud/modules");
}

/**
 * Every labeled sample's tags, fetched apart from the points: a few hundred rows that change with
 * every label written, against a hundred thousand points that change only when the embedding does.
 */
export async function getCloudLabels(): Promise<readonly CloudLabel[]> {
    return requestJson<readonly CloudLabel[]>("/cloud/labels");
}

/** Every sample's category from the newest scoring, fetched apart from the points like the labels. */
export async function getCloudCategories(): Promise<readonly CloudCategory[]> {
    return requestJson<readonly CloudCategory[]>("/cloud/suggestions");
}

/** The tags the newest scoring gives as top categories, each with its count and the lasting rank its vocabulary gives it. */
export async function getCategoryTags(): Promise<readonly TagSummary[]> {
    return requestJson<readonly TagSummary[]>("/cloud/suggestion-tags");
}
