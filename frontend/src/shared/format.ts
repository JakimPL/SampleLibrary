const BYTE_UNITS: readonly string[] = ["B", "KiB", "MiB", "GiB", "TiB"];
const BYTES_PER_UNIT_STEP = 1024;
const DECIMAL_PLACES = 1;
const DURATION_DECIMAL_PLACES = 2;
const SHORT_HASH_LENGTH = 8;
const UNSAFE_FILE_NAME_CHARACTERS = /[^\w.\- ]+/g;

export function formatBytes(bytes: number): string {
    if (bytes === 0) {
        return "0 B";
    }

    let value = bytes;
    let unitIndex = 0;
    while (value >= BYTES_PER_UNIT_STEP && unitIndex < BYTE_UNITS.length - 1) {
        value /= BYTES_PER_UNIT_STEP;
        unitIndex += 1;
    }

    const unit = BYTE_UNITS[unitIndex] ?? "B";
    const precision = unitIndex === 0 ? 0 : DECIMAL_PLACES;
    return `${value.toFixed(precision)} ${unit}`;
}

export function formatDuration(seconds: number): string {
    return `${seconds.toFixed(DURATION_DECIMAL_PLACES)} s`;
}

/**
 * A content hash's leading characters, standing in for the full value the way a git commit's
 * abbreviated SHA does -- a stable, glanceable identity for a sample or module, including one with
 * no name of its own.
 */
export function shortHash(hash: string): string {
    return hash.slice(0, SHORT_HASH_LENGTH);
}

/**
 * A name a file can be saved under, from whatever the catalog calls the thing.
 *
 * Letters, digits, spaces, dots and dashes stand as they are and every other run becomes a single
 * underscore, so a name carrying a path separator or a character a file system reserves still
 * saves. A thing the catalog names with nothing at all is saved under `fallback`.
 */
export function fileNameStem(name: string, fallback: string): string {
    const safe = name.replace(UNSAFE_FILE_NAME_CHARACTERS, "_").trim();
    return safe.length > 0 ? safe : fallback;
}
