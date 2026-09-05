import type { ReactElement } from "react";

interface ErrorNoticeProps {
    readonly message: string;
}

export function ErrorNotice({ message }: ErrorNoticeProps): ReactElement {
    return (
        <p className="error-notice" role="alert">
            {message}
        </p>
    );
}
