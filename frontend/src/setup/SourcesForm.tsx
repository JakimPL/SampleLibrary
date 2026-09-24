import { type ReactElement, useState } from "react";

import { chooseSources, type LibrarySources, type SetupState } from "../api/setup";
import { describeError } from "../shared/fetchState";
import { FolderPicker } from "./FolderPicker";

interface SourcesFormProps {
    readonly state: SetupState;
    readonly onSaved: (state: SetupState) => void;
}

type PickerTarget = "modules" | "samples" | "library";

const PICKER_TITLES: Readonly<Record<PickerTarget, string>> = {
    modules: "Choose your module collection",
    samples: "Add a folder of samples",
    library: "Choose where the library keeps its files",
};
const EXCLUSION_SEPARATOR = ",";

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

function sameSources(first: LibrarySources, second: LibrarySources): boolean {
    return JSON.stringify(first) === JSON.stringify(second);
}

function readExclusions(text: string): readonly string[] {
    return text
        .split(EXCLUSION_SEPARATOR)
        .map((pattern) => pattern.trim())
        .filter((pattern) => pattern.length > 0);
}

/**
 * The folders a library reads and where it keeps its own files, chosen with the folder browser and
 * written into the config file on save, which opens the library under them.
 */
export function SourcesForm({ state, onSaved }: SourcesFormProps): ReactElement {
    const [sources, setSources] = useState<LibrarySources>(() => initialSources(state));
    const [exclusions, setExclusions] = useState(() => sources.sample_exclusions.join(`${EXCLUSION_SEPARATOR} `));
    const [picker, setPicker] = useState<PickerTarget | null>(null);
    const [saving, setSaving] = useState(false);
    const [refusal, setRefusal] = useState<string | null>(null);

    const hasSources = sources.module_source_directory !== null || sources.sample_directories.length > 0;
    const draft: LibrarySources = { ...sources, sample_exclusions: readExclusions(exclusions) };
    const unchanged = state.sources !== null && sameSources(state.sources, draft);

    function handleChoose(target: PickerTarget, path: string): void {
        setPicker(null);
        setSources((current) => {
            switch (target) {
                case "modules":
                    return { ...current, module_source_directory: path };
                case "samples":
                    return current.sample_directories.includes(path)
                        ? current
                        : { ...current, sample_directories: [...current.sample_directories, path] };
                case "library":
                    return { ...current, library_root: path };
            }
        });
    }

    async function handleSave(): Promise<void> {
        setSaving(true);
        setRefusal(null);
        try {
            onSaved(await chooseSources(draft));
        } catch (error: unknown) {
            setRefusal(describeError(error));
        } finally {
            setSaving(false);
        }
    }

    return (
        <section className="setup-card" aria-labelledby="setup-sources-title">
            <h2 id="setup-sources-title">Your folders</h2>
            <p className="setup-hint">
                Pick where your tracker modules and your sample packs are. You can add either or both, and change them
                later.
            </p>

            <div className="setup-field">
                <h3 className="setup-field-title">Tracker modules</h3>
                <p className="setup-hint">
                    One folder holding your XM, IT, MOD and S3M files, with any folders inside it.
                </p>
                {sources.module_source_directory === null ? (
                    <button
                        type="button"
                        className="setup-button"
                        onClick={() => {
                            setPicker("modules");
                        }}
                    >
                        Choose a folder…
                    </button>
                ) : (
                    <div className="setup-folder">
                        <span className="mono">{sources.module_source_directory}</span>
                        <button
                            type="button"
                            className="setup-button"
                            onClick={() => {
                                setPicker("modules");
                            }}
                        >
                            Change…
                        </button>
                        <button
                            type="button"
                            className="setup-button"
                            onClick={() => {
                                setSources((current) => ({ ...current, module_source_directory: null }));
                            }}
                        >
                            Remove
                        </button>
                    </div>
                )}
            </div>

            <div className="setup-field">
                <h3 className="setup-field-title">Sample folders</h3>
                <p className="setup-hint">Folders of WAV, AIFF and FLAC files. They stay where they are.</p>
                {sources.sample_directories.length > 0 && (
                    <ul className="setup-folder-list">
                        {sources.sample_directories.map((directory) => (
                            <li key={directory} className="setup-folder">
                                <span className="mono">{directory}</span>
                                <button
                                    type="button"
                                    className="setup-button"
                                    onClick={() => {
                                        setSources((current) => ({
                                            ...current,
                                            sample_directories: current.sample_directories.filter(
                                                (existing) => existing !== directory,
                                            ),
                                        }));
                                    }}
                                >
                                    Remove
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
                <button
                    type="button"
                    className="setup-button"
                    onClick={() => {
                        setPicker("samples");
                    }}
                >
                    Add a folder…
                </button>
                <label className="setup-label">
                    Leave out files whose path matches, separated by commas
                    <input
                        type="text"
                        className="setup-input"
                        placeholder="*loop*, *.aif"
                        value={exclusions}
                        onChange={(event) => {
                            setExclusions(event.target.value);
                        }}
                    />
                </label>
            </div>

            <div className="setup-field">
                <h3 className="setup-field-title">Library location</h3>
                <p className="setup-hint">
                    Where the library keeps its database, the audio it takes out of modules and everything it builds.
                    Pick a drive with room to spare.
                </p>
                <div className="setup-folder">
                    <span className="mono">{sources.library_root}</span>
                    <button
                        type="button"
                        className="setup-button"
                        onClick={() => {
                            setPicker("library");
                        }}
                    >
                        Change…
                    </button>
                </div>
            </div>

            {refusal !== null && (
                <p className="error-notice" role="alert">
                    {refusal}
                </p>
            )}
            <div className="setup-actions">
                <button
                    type="button"
                    className="setup-button setup-button-primary"
                    disabled={!hasSources || saving || unchanged}
                    onClick={() => {
                        void handleSave();
                    }}
                >
                    {saving ? "Saving…" : state.sources === null ? "Save and open the library" : "Save changes"}
                </button>
                {!hasSources && <span className="setup-hint">Choose a module folder or a sample folder first.</span>}
            </div>

            {picker !== null && (
                <FolderPicker
                    title={PICKER_TITLES[picker]}
                    initialPath={picker === "modules" ? sources.module_source_directory : null}
                    onChoose={(path) => {
                        handleChoose(picker, path);
                    }}
                    onClose={() => {
                        setPicker(null);
                    }}
                />
            )}
        </section>
    );
}
