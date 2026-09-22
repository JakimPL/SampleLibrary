import { onTestFinished, vi } from "vitest";

type ChangeListener = (event: MediaQueryListEvent) => void;

export interface MatchMediaStub {
    /** Flips whether `query` matches and tells every list watching it, as a browser does on a resize. */
    readonly emit: (query: string, matches: boolean) => void;
}

/**
 * Replaces `window.matchMedia` for the rest of the test with lists that match exactly the queries in
 * `matching`, and whose `change` listeners fire through `emit`. The replacement is undone when the
 * test finishes, so the setup file's always-false stub is back for the next one.
 */
export function stubMatchMedia(matching: ReadonlySet<string>): MatchMediaStub {
    const matchesByQuery = new Map<string, boolean>([...matching].map((query) => [query, true]));
    const listenersByQuery = new Map<string, Set<ChangeListener>>();

    function listenersOf(query: string): Set<ChangeListener> {
        let listeners = listenersByQuery.get(query);
        if (listeners === undefined) {
            listeners = new Set();
            listenersByQuery.set(query, listeners);
        }
        return listeners;
    }

    const spy = vi.spyOn(window, "matchMedia").mockImplementation((query: string) => {
        const list = {
            get matches(): boolean {
                return matchesByQuery.get(query) ?? false;
            },
            media: query,
            onchange: null,
            addEventListener: (_type: string, listener: ChangeListener): void => {
                listenersOf(query).add(listener);
            },
            removeEventListener: (_type: string, listener: ChangeListener): void => {
                listenersOf(query).delete(listener);
            },
            addListener: (listener: ChangeListener): void => {
                listenersOf(query).add(listener);
            },
            removeListener: (listener: ChangeListener): void => {
                listenersOf(query).delete(listener);
            },
            dispatchEvent: (): boolean => false,
        };
        return list as unknown as MediaQueryList;
    });
    onTestFinished(() => {
        spy.mockRestore();
    });

    return {
        emit(query, matches): void {
            matchesByQuery.set(query, matches);
            const event = { matches, media: query } as MediaQueryListEvent;
            for (const listener of listenersOf(query)) {
                listener(event);
            }
        },
    };
}
