import type { PanelId } from "../workspace/panelRegistry";

/** What an address puts in front of a person: one panel, one sample, or one module. */
export type ShellView =
    | { readonly kind: "panel"; readonly panelId: PanelId }
    | { readonly kind: "sample"; readonly sampleHash: string }
    | { readonly kind: "module"; readonly moduleHash: string };

/** What a route says about its view before the address's own parameters fill it in. */
export type RouteView =
    { readonly kind: "panel"; readonly panelId: PanelId } | { readonly kind: "sample" } | { readonly kind: "module" };

export interface RouteParameters {
    readonly sampleHash?: string | undefined;
    readonly moduleHash?: string | undefined;
}

/**
 * Completes a route's view with the hash its address carries.
 *
 * Raises `Error` when an entity route arrives without its hash, which no route in the table can
 * produce.
 */
export function shellViewOf(routeView: RouteView, parameters: RouteParameters): ShellView {
    switch (routeView.kind) {
        case "panel":
            return routeView;
        case "sample": {
            if (parameters.sampleHash === undefined) {
                throw new Error("a sample route arrived without a sample hash");
            }
            return { kind: "sample", sampleHash: parameters.sampleHash };
        }
        case "module": {
            if (parameters.moduleHash === undefined) {
                throw new Error("a module route arrived without a module hash");
            }
            return { kind: "module", moduleHash: parameters.moduleHash };
        }
    }
}
