import type { ReactElement } from "react";

import type { HomeNetworkReach } from "../api/setup";

interface NetworkOptionProps {
    /** Whether the config opens the library to the home network, which the next start follows. */
    readonly chosen: boolean;
    /** Whether this run answers the home network, and where a device opens it. */
    readonly reach: HomeNetworkReach;
    readonly disabled: boolean;
    readonly onChoose: (openToNetwork: boolean) => void;
}

const NETWORK_TITLE = "Open on my home network";
const NETWORK_NOTE =
    "Phones and other computers on your network can browse and play your library. Only this computer can change it.";
const RESTART_NOTE = "Restart SampleLibrary to apply this.";
const OFF_NETWORK_NOTE = "This computer isn't on a network right now.";

function describeReach(chosen: boolean, reach: HomeNetworkReach): string | null {
    if (chosen !== reach.open) {
        return RESTART_NOTE;
    }
    if (!reach.open) {
        return null;
    }
    return reach.address === null ? OFF_NETWORK_NOTE : `On another device, open ${reach.address}`;
}

/**
 * The switch opening the library to the devices on the home network, to browse and play. The
 * application follows it from its next start, so the switch says when a restart is due, and names
 * the address a device opens while the library is open to them.
 */
export function NetworkOption({ chosen, reach, disabled, onChoose }: NetworkOptionProps): ReactElement {
    const reachNote = describeReach(chosen, reach);
    return (
        <div className="build-option">
            <input
                id="open-to-network"
                className="build-option-check"
                type="checkbox"
                aria-describedby="open-to-network-note"
                checked={chosen}
                disabled={disabled}
                onChange={(event) => {
                    onChoose(event.target.checked);
                }}
            />
            <span className="build-option-text">
                <label htmlFor="open-to-network" className="build-option-title">
                    {NETWORK_TITLE}
                </label>
                <span id="open-to-network-note" className="setup-hint">
                    {NETWORK_NOTE}
                </span>
                {reachNote !== null && <span className="setup-hint network-reach">{reachNote}</span>}
            </span>
        </div>
    );
}
