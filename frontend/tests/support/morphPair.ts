import { useMorphStore } from "../../src/morph/morphStore";

/** Chooses both ends of the morph pair outright, the first end and then the second, each through the store's own `commit`. */
export function choosePair(first: string, second: string): void {
    useMorphStore.getState().setEnd("first", first);
    useMorphStore.getState().setEnd("second", second);
}
