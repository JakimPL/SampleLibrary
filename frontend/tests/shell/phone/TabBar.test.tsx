import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useMorphStore } from "../../../src/morph/morphStore";
import { tabPanels } from "../../../src/shell/phone/phoneView";
import { pairStateOf, TabBar } from "../../../src/shell/phone/TabBar";

const TABS = tabPanels();

describe("pairStateOf", () => {
    it("reads how far the pair has come", () => {
        expect(pairStateOf(null, null)).toBe("none");
        expect(pairStateOf("a", null)).toBe("half");
        expect(pairStateOf(null, "b")).toBe("half");
        expect(pairStateOf("a", "b")).toBe("full");
    });
});

describe("TabBar", () => {
    it("offers every tab in order and marks the one in front", () => {
        render(
            <MemoryRouter>
                <TabBar tabs={TABS} activeTabId="cloud" />
            </MemoryRouter>,
        );

        const links = screen.getAllByRole("link");
        expect(links.map((link) => link.textContent)).toEqual(["Samples", "Cloud", "Modules"]);
        expect(links.map((link) => link.getAttribute("href"))).toEqual(["/", "/cloud", "/modules"]);
        expect(screen.getByRole("link", { name: "Cloud" })).toHaveAttribute("aria-current", "page");
        expect(screen.getByRole("link", { name: "Samples" })).not.toHaveAttribute("aria-current");
    });

    it("replaces the address rather than adding to the history", async () => {
        const router = createMemoryRouter([{ path: "*", element: <TabBar tabs={TABS} activeTabId="samples-list" /> }], {
            initialEntries: ["/"],
        });
        render(<RouterProvider router={router} />);

        fireEvent.click(screen.getByRole("link", { name: "Modules" }));

        await waitFor(() => {
            expect(router.state.location.pathname).toBe("/modules");
        });
        expect(router.state.historyAction).toBe("REPLACE");
    });

    it("dots the Cloud tab as the pair is built", () => {
        render(
            <MemoryRouter>
                <TabBar tabs={TABS} activeTabId="samples-list" />
            </MemoryRouter>,
        );
        expect(screen.queryByTestId("morph-pair-dot")).not.toBeInTheDocument();

        act(() => {
            useMorphStore.getState().setFirst("a");
        });
        expect(screen.getByTestId("morph-pair-dot")).toHaveClass("is-half");

        act(() => {
            useMorphStore.getState().setSecond("b");
        });
        expect(screen.getByTestId("morph-pair-dot")).not.toHaveClass("is-half");
        expect(screen.getByRole("link", { name: "Cloud" })).toContainElement(screen.getByTestId("morph-pair-dot"));
    });
});
