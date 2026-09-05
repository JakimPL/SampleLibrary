const BYTE_UNITS: readonly string[] = ["B", "KiB", "MiB", "GiB", "TiB"];
const BYTES_PER_UNIT_STEP = 1024;
const DECIMAL_PLACES = 1;

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
