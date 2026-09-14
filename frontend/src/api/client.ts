// Kept equal to `API_PREFIX` in `src/sampleserver/app.py`.
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

export type WriteMethod = "PATCH";

export interface JsonRequest {
    readonly method: WriteMethod;
    /** The JSON body to send, or `null` for a request that carries none. */
    readonly body: unknown;
}

async function readJson<T>(url: string, response: Response): Promise<T> {
    if (!response.ok) {
        throw new ApiError(response.status, await failureMessage(url, response));
    }
    return (await response.json()) as T;
}

/** What went wrong with a request, in the server's own words where it gave a `detail`. */
async function failureMessage(url: string, response: Response): Promise<string> {
    const general = `request to ${url} failed with status ${String(response.status)}`;
    const body: unknown = await Promise.resolve()
        .then(() => response.json())
        .catch(() => null);
    if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
        return `${general}: ${body.detail}`;
    }
    return general;
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
