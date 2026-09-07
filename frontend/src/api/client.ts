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

async function readJson<T>(path: string, response: Response): Promise<T> {
    if (!response.ok) {
        throw new ApiError(response.status, `request to ${path} failed with status ${String(response.status)}`);
    }
    return (await response.json()) as T;
}

export async function requestJson<T>(path: string): Promise<T> {
    return readJson<T>(path, await fetch(path));
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
    return readJson<T>(path, await fetch(path, init));
}
