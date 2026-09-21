/** The separators of the hand-label grammar, as `samplecore.labeling.labels` reads them. */
const TAG_SEPARATOR = ",";
const LEVEL_SEPARATOR = ":";
const WRITTEN_TAG_SEPARATOR = ", ";
const WRITTEN_LEVEL_SEPARATOR = ": ";

/** A tag's identity: the levels its path names, from the top level down. */
export type TagPath = readonly string[];

/** One tag of a label: the text it was written with, beside the path it names. */
interface WrittenTag {
    readonly text: string;
    readonly path: TagPath;
}

/** A tag path as a person writes it: its levels joined by the level separator. */
export function formatPath(path: TagPath): string {
    return path.join(WRITTEN_LEVEL_SEPARATOR);
}

/** The levels one written tag names, upper case and trimmed, which is the form every comparison is made in. */
function pathOf(tag: string): TagPath {
    return tag
        .split(LEVEL_SEPARATOR)
        .map((level) => level.trim().toUpperCase())
        .filter((level) => level.length > 0);
}

/** Whether the second path opens with the first, which is what makes it that tag read in more detail. */
function isPrefixOf(broader: TagPath, path: TagPath): boolean {
    return broader.length <= path.length && broader.every((level, depth) => level === path[depth]);
}

/**
 * The tags a label names, in the order they were written, each keeping the text it was written with.
 *
 * The text is what a rewrite puts back, so a tag a person typed comes back as they typed it, while
 * the path is what comparisons are made on: the reading `samplecore.labeling.labels.written_paths`
 * gives a label, over every stretch between commas that names a level.
 */
function writtenTags(label: string | null): readonly WrittenTag[] {
    if (label === null) {
        return [];
    }
    return label
        .split(TAG_SEPARATOR)
        .map((text) => ({ text: text.trim(), path: pathOf(text) }))
        .filter((written) => written.path.length > 0);
}

/** The texts a label is rewritten from, with `text` over the earliest tag it refines, or after the last. */
function placedTags(written: readonly WrittenTag[], text: string, wanted: TagPath): readonly string[] {
    const refined = new Set(written.flatMap((item, index) => (isPrefixOf(item.path, wanted) ? [index] : [])));
    if (refined.size === 0) {
        return [...written.map((item) => item.text), text];
    }
    const earliest = Math.min(...refined);
    return written.flatMap((item, index) => {
        if (index === earliest) {
            return [text];
        }
        return refined.has(index) ? [] : [item.text];
    });
}

/** The top level a label names first: its first tag's head, in the form the server keeps it. */
export function topLevelOf(label: string): string {
    const [first] = writtenTags(label);
    return first?.path[0] ?? "";
}

/**
 * Whether the label already says what a tag says: it names that tag, or a specification under it.
 *
 * A written path asserts every tag above it, so a label naming `BASS: ACOUSTIC` asserts `BASS` as
 * well -- the closure `samplecore.labeling.labels.SampleLabel.closure` takes, read as a question
 * about one tag.
 */
export function assertsTag(label: string | null, tag: string): boolean {
    const wanted = pathOf(tag);
    return writtenTags(label).some((written) => isPrefixOf(wanted, written.path));
}

/**
 * The label saying what it said and the tag as well, the more detailed of two tags on one path kept.
 *
 * A tag the label already asserts leaves the label exactly as it stands. A tag more detailed than
 * tags the label names takes the place of the earliest of them and the rest of that path's tags give
 * way to it, so `BASS` reads `BASS: ACOUSTIC` where it stood. Any other tag goes after what is
 * written. The tags that stay keep their order and the text they were typed with, and
 * `samplecore.models.annotation.LabelText` settles the whole label's spelling as the server stores it.
 */
export function withTag(label: string | null, tag: string): string {
    const wanted = pathOf(tag);
    const written = writtenTags(label);
    if (label === null || written.length === 0) {
        return formatPath(wanted);
    }
    if (written.some((item) => isPrefixOf(wanted, item.path))) {
        return label;
    }
    return placedTags(written, formatPath(wanted), wanted).join(WRITTEN_TAG_SEPARATOR);
}
