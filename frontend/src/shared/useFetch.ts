import { useEffect, useState } from "react";

import { describeError, type FetchState } from "./fetchState";

export function useFetch<T>(loader: () => Promise<T>, deps: readonly unknown[]): FetchState<T> {
    const [state, setState] = useState<FetchState<T>>({ status: "loading" });

    useEffect(() => {
        let active = true;
        setState({ status: "loading" });
        loader()
            .then((data) => {
                if (active) {
                    setState({ status: "success", data });
                }
            })
            .catch((error: unknown) => {
                if (active) {
                    setState({ status: "error", message: describeError(error) });
                }
            });
        return (): void => {
            active = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps -- `deps` is the caller-chosen dependency array
    }, deps);

    return state;
}
