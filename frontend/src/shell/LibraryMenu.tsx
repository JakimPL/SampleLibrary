import { type ReactElement, useState } from "react";
import { useNavigate } from "react-router-dom";

import { quitApplication } from "../api/setup";
import { CLOSED_PATH } from "../setup/ClosedView";
import { describeRefusal } from "../setup/refusal";
import { SETUP_PATH } from "../setup/SetupGate";
import { useSetupProbe } from "../setup/useSetupProbe";
import { DisclosureMenu } from "../shared/overlay/DisclosureMenu";

/**
 * The library's own menu: its setup page, where folders are chosen and builds run, and quitting
 * the application. It appears where the setup routes answer, which is on the machine the
 * application runs on.
 */
export function LibraryMenu(): ReactElement | null {
    const setup = useSetupProbe();
    const navigate = useNavigate();
    const [refusal, setRefusal] = useState<string | null>(null);

    async function handleQuit(): Promise<void> {
        setRefusal(null);
        try {
            await quitApplication();
            void navigate(CLOSED_PATH, { replace: true });
        } catch (error: unknown) {
            setRefusal(describeRefusal(error));
        }
    }

    if (setup === null) {
        return null;
    }
    return (
        <DisclosureMenu label="Library" className="library-menu">
            <button
                type="button"
                className="menu-action"
                onClick={() => {
                    void navigate(SETUP_PATH);
                }}
            >
                Setup
            </button>
            <button
                type="button"
                className="menu-action"
                onClick={() => {
                    void handleQuit();
                }}
            >
                Quit SampleRipper
            </button>
            {refusal !== null && (
                <p className="menu-note" role="alert">
                    {refusal}
                </p>
            )}
        </DisclosureMenu>
    );
}
