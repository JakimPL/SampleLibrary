import { requestJson } from "./client";
import type { components } from "./schema";

export type LibraryStats = components["schemas"]["LibraryStats"];

export async function getStats(): Promise<LibraryStats> {
    return requestJson<LibraryStats>("/stats");
}
