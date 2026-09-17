import { Component, type ReactElement, type ReactNode } from "react";

import { ErrorNotice } from "./ErrorNotice";
import { describeError } from "./fetchState";

interface ErrorBoundaryProps {
    readonly children: ReactNode;
}

interface ErrorBoundaryState {
    readonly message: string | null;
}

/**
 * Keeps a failed render inside the region it wraps, stating what broke where that region stands.
 *
 * The workspace is a set of panels a person arranges, plays audio in and scrolls on their own, so a
 * panel that throws says so the way a panel whose data failed already does -- an `ErrorNotice` --
 * and leaves every other panel, the layout and the person's place as they were. Trying again
 * mounts the children afresh, which is what carries a panel through a momentary failure.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
    public constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { message: null };
    }

    public static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
        return { message: describeError(error) };
    }

    public render(): ReactNode {
        const { message } = this.state;
        if (message === null) {
            return this.props.children;
        }
        return (
            <div className="error-boundary">
                <ErrorNotice message={message} />
                <button
                    type="button"
                    className="error-boundary-retry"
                    onClick={() => {
                        this.setState({ message: null });
                    }}
                >
                    Try again
                </button>
            </div>
        );
    }
}

/** The children under a boundary of their own, which is how a panel is mounted. */
export function withBoundary(children: ReactNode): ReactElement {
    return <ErrorBoundary>{children}</ErrorBoundary>;
}
