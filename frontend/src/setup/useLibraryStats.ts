import { useEffect, useState } from "react";

import { getStats, type LibraryStats } from "../api/stats";

/**
 * The open library's size, asked for when it opens and again whenever `revision` changes, keeping
 * the last answer on screen meanwhile; null while the library is closed or before its first answer.
 */
export function useLibraryStats(open: boolean, revision: string): LibraryStats | null {
    const [stats, setStats] = useState<LibraryStats | null>(null);

    useEffect(() => {
        if (!open) {
            return undefined;
        }
        let active = true;
        getStats()
            .then((found) => {
                if (active) {
                    setStats(found);
                }
            })
            .catch(() => undefined);
        return (): void => {
            active = false;
        };
    }, [open, revision]);

    return open ? stats : null;
}
