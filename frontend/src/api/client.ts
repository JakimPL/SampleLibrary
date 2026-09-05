export class ApiError extends Error {
    public readonly status: number;

    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}

export async function requestJson<T>(path: string): Promise<T> {
    const response = await fetch(path);
    if (!response.ok) {
        throw new ApiError(response.status, `request to ${path} failed with status ${String(response.status)}`);
    }
    return (await response.json()) as T;
}
