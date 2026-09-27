import { useEffect, useState } from "react";

/**
 * Whether `key` has stood unchanged for `delayMs`: false as it changes, and true once it rests.
 *
 * A pointer sweeping across many points names each for a moment only; asking the server about
 * the one it rests on, and none it passes over, keeps a sweep to one request.
 */
export function useSettled(key: string, delayMs: number): boolean {
    const [settledKey, setSettledKey] = useState<string | null>(null);

    useEffect(() => {
        const timer = window.setTimeout(() => {
            setSettledKey(key);
        }, delayMs);
        return () => {
            window.clearTimeout(timer);
        };
    }, [key, delayMs]);

    return settledKey === key;
}
