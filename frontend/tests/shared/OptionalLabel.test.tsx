import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OptionalLabel } from "../../src/shared/OptionalLabel";

describe("OptionalLabel", () => {
    it("renders the value as plain text when it is non-empty", () => {
        render(<OptionalLabel value="lead" placeholder="[unnamed]" />);

        expect(screen.getByText("lead")).toBeInTheDocument();
        expect(screen.queryByText("lead")?.tagName).not.toBe("EM");
    });

    it("renders the placeholder in italics when the value is empty", () => {
        render(<OptionalLabel value="" placeholder="[unnamed]" />);

        const placeholder = screen.getByText("[unnamed]");
        expect(placeholder.tagName).toBe("EM");
    });

    it("renders the placeholder when the value is only whitespace", () => {
        render(<OptionalLabel value="   " placeholder="[unnamed]" />);

        expect(screen.getByText("[unnamed]").tagName).toBe("EM");
    });
});
