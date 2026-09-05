export type FetchState<T> =
    | { readonly status: "loading" }
    | { readonly status: "error"; readonly message: string }
    | { readonly status: "success"; readonly data: T };

export function describeError(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
}
