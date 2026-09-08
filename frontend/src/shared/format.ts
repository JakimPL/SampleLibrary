const BYTE_UNITS: readonly string[] = ["B", "KiB", "MiB", "GiB", "TiB"];
const BYTES_PER_UNIT_STEP = 1024;
const DECIMAL_PLACES = 1;
const DURATION_DECIMAL_PLACES = 2;
const SHORT_HASH_LENGTH = 8;

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
