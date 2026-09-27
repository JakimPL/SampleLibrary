import { type ReactElement, useState } from "react";

import { chooseSources, type LibrarySources, type SetupState } from "../api/setup";
import { FolderPath } from "./FolderPath";
import { FolderPicker } from "./FolderPicker";
import { describeRefusal } from "./refusal";
import { SetupMessage, type SetupMessageText } from "./SetupMessage";
import type { SourcesDraft } from "./useSourcesDraft";

interface SourcesFormProps {
    readonly state: SetupState;
    readonly draft: SourcesDraft;
    readonly onSaved: (state: SetupState) => void;
}

type PickerTarget = "modules" | "samples" | "library";

const PICKER_TITLES: Readonly<Record<PickerTarget, string>> = {
    modules: "Choose your module folder",
    samples: "Add a sample folder",
    library: "Choose where to store the library",
};

function withChosenFolder(sources: LibrarySources, target: PickerTarget, path: string): LibrarySources {
    switch (target) {
        case "modules":
            return { ...sources, module_source_directory: path };
        case "samples":
            return sources.sample_directories.includes(path)
                ? sources
                : { ...sources, sample_directories: [...sources.sample_directories, path] };
        case "library":
            return { ...sources, library_root: path };
    }
}

interface FooterConditions {
    readonly saving: boolean;
    readonly refusal: string | null;
    readonly buildRunning: boolean;
    readonly hasSources: boolean;
    readonly saved: boolean;
}

function footerMessage(conditions: FooterConditions): SetupMessageText | null {
    if (conditions.saving) {
        return { text: "Saving…", tone: "normal" };
    }
    if (conditions.refusal !== null) {
        return { text: conditions.refusal, tone: "error" };
    }
    if (conditions.buildRunning) {
        return { text: "Wait for the build to finish or cancel it.", tone: "normal" };
    }
    if (!conditions.hasSources) {
        return { text: "Choose at least one folder first.", tone: "normal" };
    }
    return conditions.saved ? { text: "Saved.", tone: "normal" } : null;
}

/**
 * The folders a library reads and where it keeps its own files, chosen with the folder browser and
 * written into the config file on save, which opens the library under them. Every control keeps its
 * row whatever is chosen, and the footer's message line takes what the form has to say.
 */
export function SourcesForm({ state, draft, onSaved }: SourcesFormProps): ReactElement {
    const [picker, setPicker] = useState<PickerTarget | null>(null);
    const [saving, setSaving] = useState(false);
    const [refusal, setRefusal] = useState<string | null>(null);

    const sources = draft.sources;
    const configured = state.sources !== null;
    const buildRunning = state.build?.status === "running";
    const hasSources = sources.module_source_directory !== null || sources.sample_directories.length > 0;
    const message = footerMessage({
        saving,
        refusal,
        buildRunning,
        hasSources,
        saved: configured && !draft.unsaved,
    });

    function change(edit: (current: LibrarySources) => LibrarySources): void {
        setRefusal(null);
        draft.edit(edit);
    }

    async function handleSave(): Promise<void> {
        setSaving(true);
        setRefusal(null);
        try {
            const saved = await chooseSources(sources);
            onSaved(saved);
            draft.reset(saved.sources ?? sources);
        } catch (error: unknown) {
            setRefusal(describeRefusal(error));
        } finally {
            setSaving(false);
        }
    }

    return (
        <section className="setup-pane" aria-labelledby="setup-sources-title">
            <header className="setup-pane-header">
                <h2 id="setup-sources-title">Your folders</h2>
                <p className="setup-hint">
                    Choose where your tracker modules and sample packs are. You need at least one.
                </p>
            </header>

            <div className="setup-pane-body">
                <div className="setup-field">
                    <h3 className="setup-field-title">Tracker modules</h3>
                    <p className="setup-hint">A folder with your XM, IT, MOD and S3M files. Subfolders are included.</p>
                    <div className="setup-folder">
                        <FolderPath path={sources.module_source_directory} placeholder="No folder chosen" />
                        <button
                            type="button"
                            className="setup-button"
                            onClick={() => {
                                setPicker("modules");
                            }}
                        >
                            Choose…
                        </button>
                        <button
                            type="button"
                            className="setup-button"
                            disabled={sources.module_source_directory === null}
                            onClick={() => {
                                change((current) => ({ ...current, module_source_directory: null }));
                            }}
                        >
                            Remove
                        </button>
                    </div>
                </div>

                <div className="setup-field">
                    <div className="setup-field-heading">
                        <h3 className="setup-field-title">Sample folders</h3>
                        <button
                            type="button"
                            className="setup-button"
                            onClick={() => {
                                setPicker("samples");
                            }}
                        >
                            Add a folder…
                        </button>
                    </div>
                    <p className="setup-hint">Folders with WAV, AIFF or FLAC files. The files stay where they are.</p>
                    <ul className="setup-folder-list">
                        {sources.sample_directories.length === 0 && (
                            <li className="setup-folder">
                                <FolderPath path={null} placeholder="No sample folders yet" />
                            </li>
                        )}
                        {sources.sample_directories.map((directory) => (
                            <li key={directory} className="setup-folder">
                                <FolderPath path={directory} placeholder="" />
                                <button
                                    type="button"
                                    className="setup-button"
                                    onClick={() => {
                                        change((current) => ({
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
                    <label className="setup-label">
                        Skip files matching these patterns (separated by commas)
                        <input
                            type="text"
                            className="setup-input"
                            placeholder="*loop*, *.aif"
                            value={draft.exclusionsText}
                            onChange={(event) => {
                                setRefusal(null);
                                draft.setExclusionsText(event.target.value);
                            }}
                        />
                    </label>
                </div>

                <div className="setup-field">
                    <h3 className="setup-field-title">Library location</h3>
                    <p className="setup-hint">
                        Where SampleRipper stores its database and everything it creates. Choose a drive with plenty of
                        free space.
                    </p>
                    <div className="setup-folder">
                        <FolderPath path={sources.library_root} placeholder="" />
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
            </div>

            <footer className="setup-pane-footer">
                <SetupMessage message={message} />
                <button
                    type="button"
                    className="setup-button setup-button-primary"
                    disabled={!hasSources || saving || buildRunning || (configured && !draft.unsaved)}
                    onClick={() => {
                        void handleSave();
                    }}
                >
                    {configured ? "Save changes" : "Save and open the library"}
                </button>
            </footer>

            {picker !== null && (
                <FolderPicker
                    title={PICKER_TITLES[picker]}
                    initialPath={picker === "modules" ? sources.module_source_directory : null}
                    onChoose={(path) => {
                        setPicker(null);
                        change((current) => withChosenFolder(current, picker, path));
                    }}
                    onClose={() => {
                        setPicker(null);
                    }}
                />
            )}
        </section>
    );
}
