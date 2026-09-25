// Kept equal to `API_PREFIX` in `src/sampleserver/app.py`.
const API_PREFIX = "/api";

/** Where a path relative to the API's own root is actually served. */
export function apiUrl(path: string): string {
    return `${API_PREFIX}${path}`;
}

export class ApiError extends Error {
    public readonly status: number;
    /** The server's own words about the refusal, where it gave a `detail`. */
    public readonly detail: string | null;

    constructor(status: number, message: string, detail: string | null) {
        super(message);
        this.status = status;
        this.detail = detail;
    }
}

export type WriteMethod = "PATCH" | "PUT" | "POST";

export interface JsonRequest {
    readonly method: WriteMethod;
    /** The JSON body to send, or `null` for a request that carries none. */
    readonly body: unknown;
}

async function readJson<T>(url: string, response: Response): Promise<T> {
    if (!response.ok) {
        const detail = await refusalDetail(response);
        throw new ApiError(response.status, failureMessage(url, response.status, detail), detail);
    }
    return (await response.json()) as T;
}

/** The server's own words about a refusal, where it gave a `detail`, and `null` where it gave none. */
export async function refusalDetail(response: Response): Promise<string | null> {
    const body: unknown = await Promise.resolve()
        .then(() => response.json())
        .catch(() => null);
    if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
        return body.detail;
    }
    return null;
}

/** What went wrong with a request, in the server's own words where it gave a `detail`. */
function failureMessage(url: string, status: number, detail: string | null): string {
    const general = `request to ${url} failed with status ${String(status)}`;
    return detail === null ? general : `${general}: ${detail}`;
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
