import { type ReactElement, useState } from "react";

import { chooseSources, type LibrarySources, type SetupState } from "../api/setup";
import { Button } from "../shared/controls/Button";
import { FolderPath } from "./FolderPath";
import { FolderPicker } from "./FolderPicker";
import { PathRow } from "./PathRow";
import { describeRefusal } from "./refusal";
import { SetupMessage, type SetupMessageText } from "./SetupMessage";
import { SetupPane } from "./SetupPane";
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
const REMOVE_GLYPH = "×";

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

    const footer = (
        <>
            <SetupMessage message={message} />
            <Button
                variant="primary"
                disabled={!hasSources || saving || buildRunning || (configured && !draft.unsaved)}
                onClick={() => {
                    void handleSave();
                }}
            >
                {configured ? "Save changes" : "Save and open the library"}
            </Button>
        </>
    );

    return (
        <>
            <SetupPane title="Folders" titleId="setup-sources-title" footer={footer}>
                <p className="setup-lead">
                    Choose where your tracker modules and sample packs are. You need at least one.
                </p>

                <fieldset className="group">
                    <legend>Tracker modules</legend>
                    <p className="setup-hint">A folder with your XM, IT, MOD and S3M files. Subfolders are included.</p>
                    <PathRow
                        path={sources.module_source_directory}
                        placeholder="No folder chosen"
                        onBrowse={() => {
                            setPicker("modules");
                        }}
                        onClear={() => {
                            change((current) => ({ ...current, module_source_directory: null }));
                        }}
                    />
                </fieldset>

                <fieldset className="group">
                    <legend>Sample folders</legend>
                    <p className="setup-hint">Folders with WAV, AIFF or FLAC files. The files stay where they are.</p>
                    <ul className="listbox setup-folder-list">
                        {sources.sample_directories.length === 0 && (
                            <li className="listbox-row listbox-empty">
                                <FolderPath path={null} placeholder="No sample folders yet" />
                            </li>
                        )}
                        {sources.sample_directories.map((directory) => (
                            <li key={directory} className="listbox-row">
                                <FolderPath path={directory} placeholder="" />
                                <Button
                                    variant="quiet"
                                    icon
                                    aria-label="Remove"
                                    onClick={() => {
                                        change((current) => ({
                                            ...current,
                                            sample_directories: current.sample_directories.filter(
                                                (existing) => existing !== directory,
                                            ),
                                        }));
                                    }}
                                >
                                    {REMOVE_GLYPH}
                                </Button>
                            </li>
                        ))}
                    </ul>
                    <div className="group-actions">
                        <Button
                            variant="secondary"
                            onClick={() => {
                                setPicker("samples");
                            }}
                        >
                            Add a folder…
                        </Button>
                    </div>
                    <label className="setup-label">
                        Skip files matching
                        <input
                            type="text"
                            className="field"
                            placeholder="*loop*, *.aif"
                            value={draft.exclusionsText}
                            onChange={(event) => {
                                setRefusal(null);
                                draft.setExclusionsText(event.target.value);
                            }}
                        />
                    </label>
                    <p className="setup-hint">Separate patterns with commas.</p>
                </fieldset>

                <fieldset className="group">
                    <legend>Library location</legend>
                    <p className="setup-hint">
                        Where SampleRipper keeps its database and everything it creates. Choose a drive with plenty of
                        free space.
                    </p>
                    <PathRow
                        path={sources.library_root}
                        placeholder=""
                        onBrowse={() => {
                            setPicker("library");
                        }}
                        onClear={null}
                    />
                </fieldset>
            </SetupPane>

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
        </>
    );
}
