import { ApiError } from "../api/client";
import { describeError } from "../shared/fetchState";

/** Why a request failed, as the page tells a person: the server's own words where it refused, the error's otherwise. */
export function describeRefusal(error: unknown): string {
    return error instanceof ApiError && error.detail !== null ? error.detail : describeError(error);
}
