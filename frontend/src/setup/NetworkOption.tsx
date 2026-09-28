import type { ReactElement } from "react";

import type { HomeNetworkReach } from "../api/setup";
import { CheckOption } from "./CheckOption";

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
    "Phones and computers on the same network can browse and play your library, and see your folders and labels. Only this computer can change anything. Use it only on a network you trust, such as your home Wi-Fi.";
export const RESTART_NOTE = "Restart SampleRipper to apply this.";
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
 * the address a device opens while the library is open to them, on a line kept whether or not it
 * has something to say.
 */
export function NetworkOption({ chosen, reach, disabled, onChoose }: NetworkOptionProps): ReactElement {
    return (
        <CheckOption title={NETWORK_TITLE} note={NETWORK_NOTE} checked={chosen} disabled={disabled} onChange={onChoose}>
            <span className="setup-hint network-reach">{describeReach(chosen, reach)}</span>
        </CheckOption>
    );
}
