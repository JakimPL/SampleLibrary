import type { ReactElement } from "react";

import type { BuildStep, BuildView, StepState } from "../api/setup";
import { SetupMessage } from "./SetupMessage";
import { stepName } from "./stepNames";
import { describeElapsed, describeEstimate, estimateRemainingSeconds, secondsBetween, useClock } from "./timing";

interface BuildProgressProps {
    readonly build: BuildView | null;
    readonly onCancel: () => void;
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
const CLOCK_FORMAT: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };

/** "Step 3 of 12": the first step still running or waiting, counted among all; null before the run lists its steps. */
function stepPosition(steps: readonly BuildStep[]): string | null {
    if (steps.length === 0) {
        return null;
    }
    const current = steps.findIndex((step) => step.state === "running" || step.state === "waiting");
    const position = current === -1 ? steps.length : current + 1;
    return `Step ${String(position)} of ${String(steps.length)}`;
}

function describeBuildTimes(build: BuildView, now: number): string {
    if (build.status === "running") {
        const startedAt = new Date(build.started_at).toLocaleTimeString([], CLOCK_FORMAT);
        return `Started at ${startedAt} · ${describeElapsed(secondsBetween(build.started_at, now))} so far`;
    }
    return build.ended_at === null ? "" : `Took ${describeElapsed(secondsBetween(build.started_at, build.ended_at))}`;
}

function describeRunningStep(step: BuildStep, now: number): string {
    const progress = step.progress;
    if (progress !== null) {
        const count = `${progress.done.toLocaleString()} of ${progress.total.toLocaleString()}`;
        const remaining = estimateRemainingSeconds(progress);
        return remaining === null ? count : `${count} · ${describeEstimate(remaining)}`;
    }
    return step.started_at === null
        ? STEP_NOTES.running
        : `running for ${describeElapsed(secondsBetween(step.started_at, now))}`;
}

function describeStep(step: BuildStep, now: number): string {
    switch (step.state) {
        case "running":
            return describeRunningStep(step, now);
        case "done":
            return step.started_at !== null && step.ended_at !== null
                ? `took ${describeElapsed(secondsBetween(step.started_at, step.ended_at))}`
                : STEP_NOTES.done;
        case "waiting":
        case "up to date":
        case "failed":
        case "skipped":
            return STEP_NOTES[step.state];
    }
}

function StepRow({ step, now }: { readonly step: BuildStep; readonly now: number }): ReactElement {
    const progress = step.progress;
    const fraction = progress !== null && progress.total > 0 ? progress.done / progress.total : undefined;
    return (
        <li className="build-step" data-state={step.state}>
            <span className="build-step-mark" aria-hidden>
                {STEP_MARKS[step.state]}
            </span>
            <span className="build-step-name">{stepName(step.name)}</span>
            <span className="build-step-note">{describeStep(step, now)}</span>
            {step.state === "running" && (
                <progress
                    className="build-step-bar"
                    value={fraction}
                    max={1}
                    aria-label={progress?.label ?? stepName(step.name)}
                />
            )}
        </li>
    );
}

/**
 * The latest build as it runs: its heading, which step it is on and a way to cancel it on one row
 * of fixed height, how long it has taken, and every step with its time, the running one with its
 * count, estimate and bar. The end of the log opens under a build that stopped.
 */
export function BuildProgress({ build, onCancel }: BuildProgressProps): ReactElement {
    const running = build?.status === "running";
    const now = useClock(running);

    if (build === null) {
        return <p className="build-placeholder setup-hint">Builds you start show their progress here.</p>;
    }
    return (
        <section className="build-progress" aria-labelledby="build-progress-title">
            <div className="build-progress-heading">
                <h3 id="build-progress-title" className="build-progress-title">
                    {BUILD_HEADINGS[build.status]}
                </h3>
                <span className="build-progress-position">{running ? stepPosition(build.steps) : null}</span>
                {running && (
                    <button type="button" className="setup-button" onClick={onCancel}>
                        Cancel
                    </button>
                )}
            </div>
            <p className="build-progress-times setup-hint">{describeBuildTimes(build, now)}</p>
            <ol className="build-steps">
                {build.steps.map((step) => (
                    <StepRow key={step.name} step={step} now={now} />
                ))}
                {build.steps.length === 0 && <li className="setup-hint">Getting ready…</li>}
            </ol>
            {build.problem !== null && <SetupMessage message={{ text: build.problem, tone: "error" }} />}
            {build.status === "failed" && build.log_tail.length > 0 && (
                <details className="build-log">
                    <summary>Show details</summary>
                    <pre className="mono">{build.log_tail.join("\n")}</pre>
                </details>
            )}
        </section>
    );
}
