import { useMemo } from "react";
import { create } from "zustand";

import type { EntityKind, EntityRef } from "./selectionStore";

/** Where an entity stands in the listing it came from, and which entities stand either side of it. */
export interface ListingNeighbors {
    readonly previous: string | null;
    readonly next: string | null;
    /** The entity's one-based place in the listing; `null` while the listing holds no such entity. */
    readonly position: number | null;
    readonly count: number;
}

interface ListingOrderState {
    readonly orderByKind: Readonly<Record<EntityKind, readonly string[]>>;
}

interface ListingOrderActions {
    readonly publish: (kind: EntityKind, hashes: readonly string[]) => void;
}

export const INITIAL_LISTING_ORDER_STATE: ListingOrderState = {
    orderByKind: { sample: [], module: [] },
};

const NO_ORDER: readonly string[] = [];

/**
 * The order each listing shows its rows in, as the listing itself publishes it after every filter,
 * sort and grouping. A detail steps to the row before or after the one it shows through this
 * order, so walking a listing from its details follows what the person saw in the list.
 */
export const useListingOrderStore = create<ListingOrderState & ListingOrderActions>((set) => ({
    ...INITIAL_LISTING_ORDER_STATE,
    publish: (kind, hashes) => {
        set((state) => ({ orderByKind: { ...state.orderByKind, [kind]: hashes } }));
    },
}));

/** The neighbors of `hash` within `order`; an entity outside the order has none and no place. */
export function neighborsOf(order: readonly string[], hash: string): ListingNeighbors {
    const index = order.indexOf(hash);
    if (index < 0) {
        return { previous: null, next: null, position: null, count: order.length };
    }
    return {
        previous: order[index - 1] ?? null,
        next: order[index + 1] ?? null,
        position: index + 1,
        count: order.length,
    };
}

/** The neighbors of `entity` in the listing of its kind, kept live as the listing changes. */
export function useListingNeighbors(entity: EntityRef | null): ListingNeighbors {
    const order = useListingOrderStore((state) => (entity === null ? NO_ORDER : state.orderByKind[entity.kind]));
    const hash = entity?.hash ?? null;
    return useMemo(() => (hash === null ? neighborsOf(NO_ORDER, "") : neighborsOf(order, hash)), [order, hash]);
}
