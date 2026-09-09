// Mirrors `API_PREFIX` in `src/sampleserver/app.py`. The whole API lives under one path
// segment so a client route like `/samples/{hash}` and the listing endpoint behind it stay
// distinct paths, which is what lets a dev-server proxy forward one and leave the other alone.
const API_PREFIX = "/api";

/** Where a path relative to the API's own root is actually served. */
export function apiUrl(path: string): string {
    return `${API_PREFIX}${path}`;
}

export class ApiError extends Error {
    public readonly status: number;

    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}

export type WriteMethod = "PUT" | "DELETE";

export interface JsonRequest {
    readonly method: WriteMethod;
    /** The JSON body to send, or `null` for a request that carries none. */
    readonly body: unknown;
}

async function readJson<T>(url: string, response: Response): Promise<T> {
    if (!response.ok) {
        throw new ApiError(response.status, `request to ${url} failed with status ${String(response.status)}`);
    }
    return (await response.json()) as T;
}

export async function requestJson<T>(path: string): Promise<T> {
    const url = apiUrl(path);
    return readJson<T>(url, await fetch(url));
}

/** Sends a change to the server and reads back what it made of it. */
export async function sendJson<T>(path: string, request: JsonRequest): Promise<T> {
    const init: RequestInit =
        request.body === null
            ? { method: request.method }
            : {
                  method: request.method,
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(request.body),
              };
    const url = apiUrl(path);
    return readJson<T>(url, await fetch(url, init));
}
