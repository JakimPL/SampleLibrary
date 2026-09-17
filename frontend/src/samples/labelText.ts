/** The separators of the hand-label grammar, as `samplecore.labeling.labels` reads them. */
const TAG_SEPARATOR = ",";
const LEVEL_SEPARATOR = ":";
const WRITTEN_TAG_SEPARATOR = ", ";
const WRITTEN_LEVEL_SEPARATOR = ": ";

/** A tag path as a person writes it: its levels joined by the level separator. */
export function formatPath(path: readonly string[]): string {
    return path.join(WRITTEN_LEVEL_SEPARATOR);
}

/** One written tag in the form the server keeps it: upper case, one space after each colon. */
function normalizedTag(tag: string): string {
    return tag
        .split(LEVEL_SEPARATOR)
        .map((level) => level.trim().toUpperCase())
        .filter((level) => level.length > 0)
        .join(WRITTEN_LEVEL_SEPARATOR);
}

/** The top level a label names first: its first tag's head, in the form the server keeps it. */
export function topLevelOf(label: string): string {
    const [firstTag = ""] = label.split(TAG_SEPARATOR);
    const [topLevel = ""] = normalizedTag(firstTag).split(WRITTEN_LEVEL_SEPARATOR);
    return topLevel;
}

/** Whether a written label already asserts the tag, at whatever position and casing it was written in. */
export function holdsTag(label: string | null, tag: string): boolean {
    if (label === null) {
        return false;
    }
    const wanted = normalizedTag(tag);
    return label.split(TAG_SEPARATOR).some((written) => normalizedTag(written) === wanted);
}

/** The label with the tag appended after what it already says, or as it was when it already holds the tag. */
export function withTag(label: string | null, tag: string): string {
    if (label === null || label.trim().length === 0) {
        return tag;
    }
    return holdsTag(label, tag) ? label : `${label}${WRITTEN_TAG_SEPARATOR}${tag}`;
}
