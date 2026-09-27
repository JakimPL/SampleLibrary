import { type ReactElement, useState } from "react";
import { Link } from "react-router-dom";

import {
    type BuildDevice,
    type BuildTarget,
    cancelBuild,
    chooseOptions,
    type SetupState,
    startBuild,
} from "../api/setup";
import type { LibraryStats } from "../api/stats";
import { Button } from "../shared/controls/Button";
import { buttonClassName } from "../shared/controls/buttonClassName";
import { ActionSheet } from "../shared/overlay/ActionSheet";
import { BuildProgress } from "./BuildProgress";
import { CheckOption } from "./CheckOption";
import { NetworkOption } from "./NetworkOption";
import { describeRefusal } from "./refusal";
import { SetupMessage, type SetupMessageText } from "./SetupMessage";
import { SetupPane } from "./SetupPane";
import { useLibraryStats } from "./useLibraryStats";

interface LibraryPanelProps {
    readonly state: SetupState;
    /** Whether the folders pane holds edits beyond the folders the library opened with, which holds builds back. */
    readonly unsavedChanges: boolean;
    readonly onChanged: (state: SetupState) => void;
}

const BUILD_TITLE = "Build my library";
const BUILD_NOTE =
    "Reads your modules and samples and finds duplicates. Run it again after adding files; only new files are read.";
const CLOUD_TITLE = "Build the cloud";
const CLOUD_NOTE = "Analyzes every sample, suggests categories and lays out the cloud.";
const CONFIRMATION_TITLE = "Build the cloud without an NVIDIA graphics card?";
const CONFIRMATION_NOTE =
    "On the processor, analyzing a large collection can take a day or more. You can build the cloud later.";
const DEFAULT_BUILD_CLOUD = true;
const DEFAULT_OPEN_TO_NETWORK = false;

function countOf(count: number, noun: string): string {
    return `${count.toLocaleString()} ${noun}${count === 1 ? "" : "s"}`;
}

function describeStats(stats: LibraryStats | null, building: boolean): string {
    if (stats === null) {
        return "Your library is open.";
    }
    if (stats.sample_count === 0) {
        return building ? "Your library is empty so far." : "Your library is empty. Build it to fill it.";
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

function describeDevice(device: BuildDevice | null): string {
    if (device === null) {
        return "Checking for an NVIDIA graphics card…";
    }
    return device.card === null
        ? "Builds use the processor, so building the cloud takes a long time."
        : `Builds use your ${device.card}.`;
}

interface OpenLibraryButtonProps {
    readonly ready: boolean;
    /** Whether opening is the next step, once the library holds samples. */
    readonly primary: boolean;
}

function OpenLibraryButton({ ready, primary }: OpenLibraryButtonProps): ReactElement {
    if (!ready) {
        return (
            <Button variant="secondary" disabled>
                Open the library
            </Button>
        );
    }
    return (
        <Link className={buttonClassName({ variant: primary ? "primary" : "secondary" })} to="/">
            Open the library
        </Link>
    );
}

/**
 * Where a person builds the open library, watches it happen and goes on to it: the library's status
 * and size, the build with its cloud switch and the device it computes on, the switch opening the
 * library to the home network, the latest build's progress, and a footer holding Build and Open,
 * the primary one being the next step: Build while the library is empty, Open once it holds
 * samples. A build going on to the cloud without an NVIDIA card asks first, since the processor
 * takes many hours over a large collection.
 */
export function LibraryPanel({ state, unsavedChanges, onChanged }: LibraryPanelProps): ReactElement {
    const [refusal, setRefusal] = useState<string | null>(null);
    const [confirming, setConfirming] = useState(false);
    const build = state.build;
    const running = build?.status === "running";
    const ready = state.status === "ready";
    const device = state.build_device;
    const buildCloud = state.options?.build_cloud ?? DEFAULT_BUILD_CLOUD;
    const openToNetwork = state.options?.open_to_network ?? DEFAULT_OPEN_TO_NETWORK;
    const canStart = ready && !running && !unsavedChanges && device !== null;
    const stats = useLibraryStats(ready, `${build?.started_at ?? ""} ${build?.status ?? ""}`);
    const empty = stats === null || stats.sample_count === 0;
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

    function start(target: BuildTarget): void {
        void act(() => startBuild(target));
    }

    function handleBuild(): void {
        if (!buildCloud) {
            start("catalog");
        } else if (device?.card === null) {
            setConfirming(true);
        } else {
            start("all");
        }
    }

    const footer = (
        <div className="setup-footer-actions">
            <Button variant={canStart && empty ? "primary" : "secondary"} disabled={!canStart} onClick={handleBuild}>
                {BUILD_TITLE}
            </Button>
            <OpenLibraryButton ready={ready} primary={ready && !empty} />
        </div>
    );

    return (
        <>
            <SetupPane title="Library" titleId="setup-library-title" footer={footer}>
                <SetupMessage message={status} className="setup-status" />

                <fieldset className="group">
                    <legend>Build</legend>
                    <p className="setup-hint">{BUILD_NOTE}</p>
                    <CheckOption
                        title={CLOUD_TITLE}
                        note={CLOUD_NOTE}
                        checked={buildCloud}
                        disabled={state.options === null || running}
                        onChange={(chosen) => {
                            void act(() => chooseOptions({ build_cloud: chosen, open_to_network: openToNetwork }));
                        }}
                    />
                    <p className="setup-hint build-device">{describeDevice(device)}</p>
                </fieldset>

                <fieldset className="group">
                    <legend>Sharing</legend>
                    <NetworkOption
                        chosen={openToNetwork}
                        reach={state.home_network}
                        disabled={state.options === null}
                        onChoose={(chosen) => {
                            void act(() => chooseOptions({ build_cloud: buildCloud, open_to_network: chosen }));
                        }}
                    />
                </fieldset>

                <BuildProgress
                    build={build}
                    onCancel={() => {
                        void act(cancelBuild);
                    }}
                />
            </SetupPane>
            {confirming && (
                <ActionSheet
                    title={CONFIRMATION_TITLE}
                    actions={[
                        {
                            id: "cloud",
                            label: "Build with the cloud",
                            disabled: false,
                            run: () => {
                                start("all");
                            },
                        },
                        {
                            id: "catalog",
                            label: "Build without the cloud",
                            disabled: false,
                            run: () => {
                                start("catalog");
                            },
                        },
                        { id: "cancel", label: "Cancel", disabled: false, run: () => undefined },
                    ]}
                    onClose={() => {
                        setConfirming(false);
                    }}
                >
                    <p className="setup-hint">{CONFIRMATION_NOTE}</p>
                </ActionSheet>
            )}
        </>
    );
}
