import { type ReactElement, useState } from "react";
import { Link } from "react-router-dom";

import {
    type BuildStep,
    type BuildTarget,
    type BuildView,
    cancelBuild,
    type SetupState,
    startBuild,
    type StepState,
} from "../api/setup";
import { describeError } from "../shared/fetchState";
import { stepName } from "./stepNames";

interface BuildPanelProps {
    readonly state: SetupState;
    readonly onChanged: (state: SetupState) => void;
}

const STEP_MARKS: Readonly<Record<StepState, string>> = {
    waiting: "○",
    "up to date": "✓",
    running: "◐",
    done: "✓",
    failed: "✕",
    skipped: "–",
};
const STEP_NOTES: Readonly<Record<StepState, string>> = {
    waiting: "waiting",
    "up to date": "already up to date",
    running: "working…",
    done: "done",
    failed: "stopped",
    skipped: "not reached",
};
const BUILD_HEADINGS: Readonly<Record<BuildView["status"], string>> = {
    running: "Building your library…",
    completed: "Your library is ready",
    failed: "The build stopped",
    canceled: "The build was canceled",
};

function StepRow({ step }: { readonly step: BuildStep }): ReactElement {
    const progress = step.progress;
    const fraction = progress !== null && progress.total > 0 ? progress.done / progress.total : null;
    return (
        <li className="build-step" data-state={step.state}>
            <span className="build-step-mark" aria-hidden>
                {STEP_MARKS[step.state]}
            </span>
            <span className="build-step-name">{stepName(step.name)}</span>
            <span className="build-step-note">
                {step.state === "running" && progress !== null
                    ? `${progress.done.toLocaleString()} of ${progress.total.toLocaleString()}`
                    : STEP_NOTES[step.state]}
            </span>
            {step.state === "running" && fraction !== null && (
                <progress className="build-step-bar" value={fraction} max={1} aria-label={progress?.label} />
            )}
        </li>
    );
}

/**
 * Where a person starts building the open library and watches it happen: the steps in order, the
 * running one's count, and the end of the log when a step stops.
 */
export function BuildPanel({ state, onChanged }: BuildPanelProps): ReactElement {
    const [refusal, setRefusal] = useState<string | null>(null);
    const build = state.build;
    const running = build?.status === "running";

    async function act(action: () => Promise<SetupState>): Promise<void> {
        setRefusal(null);
        try {
            onChanged(await action());
        } catch (error: unknown) {
            setRefusal(describeError(error));
        }
    }

    function handleStart(target: BuildTarget): void {
        void act(() => startBuild(target));
    }

    return (
        <section className="setup-card" aria-labelledby="setup-build-title">
            <h2 id="setup-build-title">{build === null ? "Build your library" : BUILD_HEADINGS[build.status]}</h2>
            {state.status === "starting" && (
                <p className="setup-hint">
                    Opening your library. The first time takes a moment while its database is created.
                </p>
            )}
            {state.status === "failed" && state.problem !== null && (
                <p className="error-notice" role="alert">
                    {state.problem}
                </p>
            )}
            {state.status === "ready" && !running && (
                <div className="build-choices">
                    <div className="build-choice">
                        <button
                            type="button"
                            className={
                                build?.status === "completed" ? "setup-button" : "setup-button setup-button-primary"
                            }
                            onClick={() => {
                                handleStart("catalog");
                            }}
                        >
                            Scan my folders
                        </button>
                        <p className="setup-hint">
                            Reads every module and sample, draws their waveforms and finds near-duplicates. Run it again
                            whenever you add files; only what changed is read.
                        </p>
                    </div>
                    <div className="build-choice">
                        <button
                            type="button"
                            className="setup-button"
                            onClick={() => {
                                handleStart("all");
                            }}
                        >
                            Scan and build the cloud
                        </button>
                        <p className="setup-hint">
                            Also listens to every sample, suggests categories and lays out the cloud. This takes hours
                            on a large collection and runs best with an NVIDIA graphics card.
                        </p>
                    </div>
                </div>
            )}
            {build !== null && (
                <>
                    <ol className="build-steps">
                        {build.steps.map((step) => (
                            <StepRow key={step.name} step={step} />
                        ))}
                        {build.steps.length === 0 && <li className="setup-hint">Preparing the build…</li>}
                    </ol>
                    {build.problem !== null && (
                        <p className="error-notice" role="alert">
                            {build.problem}
                        </p>
                    )}
                    {build.status === "failed" && build.log_tail.length > 0 && (
                        <details className="build-log">
                            <summary>What the step wrote last</summary>
                            <pre className="mono">{build.log_tail.join("\n")}</pre>
                        </details>
                    )}
                </>
            )}
            {refusal !== null && (
                <p className="error-notice" role="alert">
                    {refusal}
                </p>
            )}
            <div className="setup-actions">
                {running && (
                    <button
                        type="button"
                        className="setup-button"
                        onClick={() => {
                            void act(cancelBuild);
                        }}
                    >
                        Cancel the build
                    </button>
                )}
                {state.status === "ready" && (
                    <Link
                        className={build?.status === "completed" ? "setup-button setup-button-primary" : "setup-button"}
                        to="/"
                    >
                        Open the library
                    </Link>
                )}
            </div>
        </section>
    );
}
