import type { ReactElement } from "react";

import { classNames } from "../shared/classNames";

export type MessageTone = "normal" | "error";

export interface SetupMessageText {
    readonly text: string;
    readonly tone: MessageTone;
}

interface SetupMessageProps {
    readonly message: SetupMessageText | null;
    readonly className?: string;
}

/**
 * A line reserved for what a pane has to say, rendered empty while it has nothing, so a message
 * arriving or leaving moves none of the controls around it.
 */
export function SetupMessage({ message, className }: SetupMessageProps): ReactElement {
    return (
        <p
            className={classNames("setup-message", className)}
            data-tone={message?.tone ?? "normal"}
            role={message?.tone === "error" ? "alert" : "status"}
        >
            {message?.text}
        </p>
    );
}
