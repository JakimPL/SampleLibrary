import type { components } from "../api/schema";

type Loop = components["schemas"]["Loop"];

const NO_LOOP_LABEL = "—";

export function formatLoop(loop: Loop | null | undefined): string {
    if (!loop) {
        return NO_LOOP_LABEL;
    }

    return `${String(loop.begin)}–${String(loop.end)} (${loop.mode})`;
}
