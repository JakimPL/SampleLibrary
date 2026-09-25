import { useState } from "react";

import type { LibrarySources, SetupState } from "../api/setup";

export const EXCLUSION_SEPARATOR = ",";

export interface SourcesDraft {
    /** The folders as edited, with the exclusion patterns read from their text. */
    readonly sources: LibrarySources;
    readonly exclusionsText: string;
    /** Whether the edits differ from the folders the open library was saved with. */
    readonly unsaved: boolean;
    readonly edit: (change: (current: LibrarySources) => LibrarySources) => void;
    readonly setExclusionsText: (text: string) => void;
    /** Starts editing afresh from the folders a save answered with. */
    readonly reset: (sources: LibrarySources) => void;
}

function initialSources(state: SetupState): LibrarySources {
    return (
        state.sources ?? {
            library_root: state.suggested_library_root,
            module_source_directory: null,
            sample_directories: [],
            sample_exclusions: [],
        }
    );
}

function joinExclusions(sources: LibrarySources): string {
    return sources.sample_exclusions.join(`${EXCLUSION_SEPARATOR} `);
}

function readExclusions(text: string): readonly string[] {
    return text
        .split(EXCLUSION_SEPARATOR)
        .map((pattern) => pattern.trim())
        .filter((pattern) => pattern.length > 0);
}

function sameList(first: readonly string[], second: readonly string[]): boolean {
    return first.length === second.length && first.every((item, index) => item === second[index]);
}

function sameSources(first: LibrarySources, second: LibrarySources): boolean {
    return (
        first.library_root === second.library_root &&
        first.module_source_directory === second.module_source_directory &&
        sameList(first.sample_directories, second.sample_directories) &&
        sameList(first.sample_exclusions, second.sample_exclusions)
    );
}

/**
 * The folders a person is choosing, held apart from the saved ones, so the folders pane edits them
 * and the library pane holds its builds back while they differ.
 */
export function useSourcesDraft(state: SetupState): SourcesDraft {
    const [folders, setFolders] = useState<LibrarySources>(() => initialSources(state));
    const [exclusionsText, setExclusionsText] = useState(() => joinExclusions(folders));

    const sources: LibrarySources = { ...folders, sample_exclusions: readExclusions(exclusionsText) };
    return {
        sources,
        exclusionsText,
        unsaved: state.sources !== null && !sameSources(state.sources, sources),
        edit: setFolders,
        setExclusionsText,
        reset: (saved) => {
            setFolders(saved);
            setExclusionsText(joinExclusions(saved));
        },
    };
}
