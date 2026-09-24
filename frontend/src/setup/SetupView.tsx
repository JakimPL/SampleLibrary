import { type ReactElement, useState } from "react";

import { quitApplication } from "../api/setup";
import { describeError } from "../shared/fetchState";
import { Loading } from "../shared/Loading";
import { BuildPanel } from "./BuildPanel";
import { SourcesForm } from "./SourcesForm";
import { useSetupState } from "./useSetupState";

/**
 * The application's own page: where a person names their folders, opens the library, builds it and
 * closes the application, all without a terminal or a config file.
 */
export function SetupView(): ReactElement {
    const { source, accept } = useSetupState();
    const [closed, setClosed] = useState(false);
    const [quitRefusal, setQuitRefusal] = useState<string | null>(null);

    async function handleQuit(): Promise<void> {
        try {
            await quitApplication();
            setClosed(true);
        } catch (error: unknown) {
            setQuitRefusal(describeError(error));
        }
    }

    if (closed) {
        return (
            <main className="setup-page">
                <section className="setup-card">
                    <h1>SampleLibrary has closed</h1>
                    <p className="setup-hint">You can close this tab.</p>
                </section>
            </main>
        );
    }

    return (
        <main className="setup-page">
            <header className="setup-header">
                <h1>SampleLibrary</h1>
                {source.status === "ready" && (
                    <button
                        type="button"
                        className="setup-button"
                        onClick={() => {
                            void handleQuit();
                        }}
                    >
                        Quit
                    </button>
                )}
            </header>
            {quitRefusal !== null && (
                <p className="error-notice" role="alert">
                    {quitRefusal}
                </p>
            )}
            {source.status === "loading" && <Loading />}
            {source.status === "error" && (
                <p className="error-notice" role="alert">
                    Can&apos;t reach SampleLibrary: {source.message}
                </p>
            )}
            {source.status === "absent" && (
                <section className="setup-card">
                    <h2>Setup isn&apos;t available here</h2>
                    <p className="setup-hint">
                        This server only shows the library. To choose folders and build the library, start SampleLibrary
                        with `samplelibrary app`.
                    </p>
                </section>
            )}
            {source.status === "ready" && (
                <>
                    {source.state.sources === null && (
                        <p className="setup-intro">
                            Welcome! Tell SampleLibrary where your modules and samples are, and it will build a library
                            you can browse and play.
                        </p>
                    )}
                    <SourcesForm key={source.state.config_path} state={source.state} onSaved={accept} />
                    {source.state.sources !== null && <BuildPanel state={source.state} onChanged={accept} />}
                </>
            )}
        </main>
    );
}
