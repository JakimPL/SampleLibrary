import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ThemeMenu } from "../../src/theme/ThemeMenu";
import { useThemeStore } from "../../src/theme/themeStore";

describe("ThemeMenu", () => {
    it("lists every theme option, including OpenMPT", () => {
        render(<ThemeMenu />);

        const options = screen.getByLabelText("Theme").querySelectorAll("option");
        expect(Array.from(options).map((option) => option.textContent)).toEqual(["System", "Light", "Dark", "OpenMPT"]);
    });

    it("reflects the store's current preference", () => {
        useThemeStore.getState().setPreference("dark");

        render(<ThemeMenu />);

        expect(screen.getByLabelText<HTMLSelectElement>("Theme").value).toBe("dark");
    });

    it("switches the theme preference on selection", () => {
        render(<ThemeMenu />);

        fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "openmpt" } });

        expect(useThemeStore.getState().preference).toBe("openmpt");
    });
});
