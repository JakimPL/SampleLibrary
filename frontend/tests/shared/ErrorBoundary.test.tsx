import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "../../src/shared/ErrorBoundary";

const FAILURE = "the badge read a label that was not there";

function Throwing({ failing }: { readonly failing: boolean }): React.ReactElement {
    if (failing) {
        throw new Error(FAILURE);
    }
    return <p>panel</p>;
}

describe("ErrorBoundary", () => {
    beforeEach(() => {
        // React reports a caught error to the console itself, which the suite reads as noise.
        vi.spyOn(console, "error").mockImplementation(() => undefined);
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("shows what the children render while they render", () => {
        render(
            <ErrorBoundary>
                <Throwing failing={false} />
            </ErrorBoundary>,
        );

        expect(screen.getByText("panel")).toBeInTheDocument();
    });

    it("states what broke and leaves what stands beside it alone", () => {
        render(
            <>
                <ErrorBoundary>
                    <Throwing failing />
                </ErrorBoundary>
                <p>another panel</p>
            </>,
        );

        expect(screen.getByRole("alert")).toHaveTextContent(FAILURE);
        expect(screen.getByText("another panel")).toBeInTheDocument();
    });

    it("mounts the children afresh when asked to try again", async () => {
        let failing = true;
        function Recovering(): React.ReactElement {
            return <Throwing failing={failing} />;
        }
        render(
            <ErrorBoundary>
                <Recovering />
            </ErrorBoundary>,
        );
        failing = false;

        await userEvent.click(screen.getByRole("button", { name: "Try again" }));

        expect(screen.getByText("panel")).toBeInTheDocument();
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
});
