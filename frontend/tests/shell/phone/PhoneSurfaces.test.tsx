import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PhoneSurfaces } from "../../../src/shell/phone/PhoneSurfaces";
import type { PhoneTab } from "../../../src/shell/phone/phoneView";

const TABS: readonly PhoneTab[] = [
    {
        id: "samples-list",
        title: "Samples",
        shortTitle: "Samples",
        icon: "samples",
        component: () => <p>samples surface</p>,
        path: "/",
    },
    {
        id: "cloud",
        title: "Cloud",
        shortTitle: "Cloud",
        icon: "cloud",
        component: () => <p>cloud surface</p>,
        path: "/cloud",
    },
];

/** The surface titled `title`, found by its label since a hidden region carries no accessible name. */
function surface(title: string): HTMLElement {
    const element = document.querySelector<HTMLElement>(`section.phone-surface[aria-label="${title}"]`);
    if (element === null) {
        throw new Error(`no surface is titled ${title}`);
    }
    return element;
}

describe("PhoneSurfaces", () => {
    it("mounts a tab on its first visit and keeps it mounted out of sight afterwards", () => {
        const { rerender } = render(<PhoneSurfaces tabs={TABS} activeTabId="samples-list" />);
        expect(screen.getByText("samples surface")).toBeInTheDocument();
        expect(screen.queryByText("cloud surface")).not.toBeInTheDocument();

        rerender(<PhoneSurfaces tabs={TABS} activeTabId="cloud" />);

        expect(screen.getByText("cloud surface")).toBeInTheDocument();
        expect(screen.getByText("samples surface")).toBeInTheDocument();
        expect(surface("Samples")).toHaveAttribute("aria-hidden", "true");
        expect(surface("Samples")).toHaveAttribute("inert");
        expect(surface("Samples")).toHaveAttribute("data-active", "false");
        expect(surface("Cloud")).not.toHaveAttribute("inert");
        expect(surface("Cloud")).toHaveAttribute("data-active", "true");
    });

    it("hides every surface while a page covers them", () => {
        const { rerender } = render(<PhoneSurfaces tabs={TABS} activeTabId="samples-list" />);

        rerender(<PhoneSurfaces tabs={TABS} activeTabId={null} />);

        expect(surface("Samples")).toHaveAttribute("inert");
        expect(screen.queryByText("cloud surface")).not.toBeInTheDocument();
    });
});
