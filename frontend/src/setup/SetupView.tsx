import { type ReactElement, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { quitApplication, type SetupState } from "../api/setup";
import { Loading } from "../shared/Loading";
import { CLOSED_PATH } from "./ClosedView";
import { LibraryPanel } from "./LibraryPanel";
import { describeRefusal } from "./refusal";
import { SetupMessage } from "./SetupMessage";
import { SourcesForm } from "./SourcesForm";
import { lastKnownState, type SetupSource, useSetupState } from "./useSetupState";
import { useSourcesDraft } from "./useSourcesDraft";

interface SetupPanesProps {
    readonly state: SetupState;
    readonly onChanged: (state: SetupState) => void;
}

/** The folders beside the library, sharing the folders being edited so the library holds its builds while they differ. */
function SetupPanes({ state, onChanged }: SetupPanesProps): ReactElement {
    const draft = useSourcesDraft(state);
    return (
        <div className="setup-panes">
            <SourcesForm state={state} draft={draft} onSaved={onChanged} />
            <LibraryPanel state={state} unsavedChanges={draft.unsaved} onChanged={onChanged} />
        </div>
    );
}

function OpenLibraryButton({ state }: { readonly state: SetupState | null }): ReactElement {
    if (state?.status !== "ready") {
        return (
            <button type="button" className="setup-button" disabled>
                Open the library
            </button>
        );
    }
    return (
        <Link
            className={state.build?.status === "completed" ? "setup-button setup-button-primary" : "setup-button"}
            to="/"
        >
            Open the library
        </Link>
    );
}

function SetupPlaceholder({ source }: { readonly source: SetupSource }): ReactElement | null {
    switch (source.status) {
        case "loading":
            return <Loading />;
        case "absent":
            return (
                <section className="setup-card">
                    <h2>Setup isn&apos;t available here</h2>
                    <p className="setup-hint">
                        This server only shows the library. To choose folders and build the library, start SampleLibrary
                        with `samplelibrary app`.
                    </p>
                </section>
            );
        case "unreachable":
        case "ready":
            return null;
    }
}

/**
 * The application's own page: where a person names their folders, opens the library, builds it and
 * closes the application, all without a terminal or a config file. On a desktop the folders and the
 * library sit side by side and fill the window; every control keeps its place in every state.
 */
export function SetupView(): ReactElement {
    const { source, accept } = useSetupState();
    const navigate = useNavigate();
    const [quitRefusal, setQuitRefusal] = useState<string | null>(null);
    const state = lastKnownState(source);
    const notice =
        quitRefusal ?? (source.status === "unreachable" ? `Can't reach SampleLibrary: ${source.message}` : null);

    async function handleQuit(): Promise<void> {
        setQuitRefusal(null);
        try {
            await quitApplication();
            void navigate(CLOSED_PATH, { replace: true });
        } catch (error: unknown) {
            setQuitRefusal(describeRefusal(error));
        }
    }

    return (
        <main className="setup-page">
            <header className="setup-header">
                <h1>SampleLibrary</h1>
                <SetupMessage
                    message={notice === null ? null : { text: notice, tone: "error" }}
                    className="setup-notice"
                />
                <div className="setup-header-actions">
                    <OpenLibraryButton state={state} />
                    <button
                        type="button"
                        className="setup-button"
                        disabled={state === null}
                        onClick={() => {
                            void handleQuit();
                        }}
                    >
                        Quit
                    </button>
                </div>
            </header>
            {state === null ? (
                <SetupPlaceholder source={source} />
            ) : (
                <SetupPanes key={state.config_path} state={state} onChanged={accept} />
            )}
        </main>
    );
}
