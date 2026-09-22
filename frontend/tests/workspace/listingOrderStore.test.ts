import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { neighborsOf, useListingNeighbors, useListingOrderStore } from "../../src/workspace/listingOrderStore";

describe("neighborsOf", () => {
    it("names the rows either side of a hash and its place among them", () => {
        expect(neighborsOf(["a", "b", "c"], "b")).toEqual({ previous: "a", next: "c", position: 2, count: 3 });
    });

    it("leaves an edge without a neighbor beyond it", () => {
        expect(neighborsOf(["a", "b"], "a")).toEqual({ previous: null, next: "b", position: 1, count: 2 });
        expect(neighborsOf(["a", "b"], "b")).toEqual({ previous: "a", next: null, position: 2, count: 2 });
    });

    it("gives a hash outside the listing no place and no neighbors", () => {
        expect(neighborsOf(["a"], "z")).toEqual({ previous: null, next: null, position: null, count: 1 });
    });
});

describe("useListingNeighbors", () => {
    it("follows the listing of the entity's own kind as it is published", () => {
        const { result } = renderHook(() => useListingNeighbors({ kind: "module", hash: "m2" }));
        expect(result.current.position).toBeNull();

        act(() => {
            useListingOrderStore.getState().publish("sample", ["m1", "m2"]);
        });
        expect(result.current.position).toBeNull();

        act(() => {
            useListingOrderStore.getState().publish("module", ["m1", "m2", "m3"]);
        });
        expect(result.current).toEqual({ previous: "m1", next: "m3", position: 2, count: 3 });
    });

    it("stands nowhere while there is no entity", () => {
        const { result } = renderHook(() => useListingNeighbors(null));

        expect(result.current).toEqual({ previous: null, next: null, position: null, count: 0 });
    });
});
