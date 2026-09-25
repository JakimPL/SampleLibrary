import { type ReactElement, useState } from "react";

import { type BuildTarget, cancelBuild, type SetupState, startBuild } from "../api/setup";
import type { LibraryStats } from "../api/stats";
import { BuildProgress } from "./BuildProgress";
import { describeRefusal } from "./refusal";
import { SetupMessage, type SetupMessageText } from "./SetupMessage";
import { useLibraryStats } from "./useLibraryStats";

interface LibraryPanelProps {
    readonly state: SetupState;
    /** Whether the folders pane holds edits beyond the folders the library opened with, which holds builds back. */
    readonly unsavedChanges: boolean;
    readonly onChanged: (state: SetupState) => void;
}

interface BuildChoice {
    readonly target: BuildTarget;
    readonly title: string;
    readonly note: string;
}

const BUILD_CHOICES: readonly BuildChoice[] = [
    {
        target: "catalog",
        title: "Scan my folders",
        note: "Reads your modules and samples and finds duplicates. Run it again after adding files; only new files are read.",
    },
    {
        target: "all",
        title: "Scan and build the cloud",
        note: "Also analyzes every sample, suggests categories and builds the cloud. This can take hours for a large collection, and it is faster with an NVIDIA graphics card.",
    },
];

function countOf(count: number, noun: string): string {
    return `${count.toLocaleString()} ${noun}${count === 1 ? "" : "s"}`;
}

function describeStats(stats: LibraryStats | null, building: boolean): string {
    if (stats === null) {
        return "Your library is open.";
    }
    if (stats.sample_count === 0) {
        return building ? "Your library is empty so far." : "Your library is empty. Scan your folders to fill it.";
    }
    const modules = stats.module_count > 0 ? ` and ${countOf(stats.module_count, "module")}` : "";
    return `Your library holds ${countOf(stats.sample_count, "sample")}${modules}.`;
}

function libraryStatus(state: SetupState, unsavedChanges: boolean, stats: LibraryStats | null): SetupMessageText {
    const building = state.build?.status === "running";
    switch (state.status) {
        case "unconfigured":
            return { text: "Welcome! Choose your folders, then save to open the library.", tone: "normal" };
        case "starting":
            return { text: "Opening your library. The first time can take a moment.", tone: "normal" };
        case "failed":
            return { text: state.problem ?? "The library couldn't open.", tone: "error" };
        case "ready":
            return unsavedChanges
                ? { text: "Save your folder changes first.", tone: "normal" }
                : { text: describeStats(stats, building), tone: "normal" };
    }
}

/**
 * Where a person builds the open library and watches it happen: the library's status and size, the
 * two builds on cards that keep their place in every state, and the latest build's progress.
 */
export function LibraryPanel({ state, unsavedChanges, onChanged }: LibraryPanelProps): ReactElement {
    const [refusal, setRefusal] = useState<string | null>(null);
    const build = state.build;
    const running = build?.status === "running";
    const canStart = state.status === "ready" && !running && !unsavedChanges;
    const stats = useLibraryStats(state.status === "ready", `${build?.started_at ?? ""} ${build?.status ?? ""}`);
    const status =
        refusal !== null ? { text: refusal, tone: "error" as const } : libraryStatus(state, unsavedChanges, stats);

    async function act(action: () => Promise<SetupState>): Promise<void> {
        setRefusal(null);
        try {
            onChanged(await action());
        } catch (error: unknown) {
            setRefusal(describeRefusal(error));
        }
    }

    return (
        <section className="setup-pane" aria-labelledby="setup-library-title">
            <header className="setup-pane-header">
                <h2 id="setup-library-title">Your library</h2>
                <SetupMessage message={status} className="setup-status" />
            </header>

            <div className="setup-pane-body setup-pane-body-tall">
                <div className="build-choices">
                    {BUILD_CHOICES.map((choice) => (
                        <button
                            key={choice.target}
                            type="button"
                            className="build-choice"
                            disabled={!canStart}
                            data-running={running && build.target === choice.target}
                            aria-label={choice.title}
                            aria-describedby={`build-choice-${choice.target}`}
                            onClick={() => {
                                void act(() => startBuild(choice.target));
                            }}
                        >
                            <span className="build-choice-title">{choice.title}</span>
                            <span id={`build-choice-${choice.target}`} className="build-choice-note">
                                {choice.note}
                            </span>
                        </button>
                    ))}
                </div>
                <BuildProgress
                    build={build}
                    onCancel={() => {
                        void act(cancelBuild);
                    }}
                />
            </div>
        </section>
    );
}
