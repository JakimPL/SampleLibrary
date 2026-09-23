import type { ReactElement } from "react";

/** What the cloud paints its samples by: the listening model's category, or the hand labels. */
export type ColoringMode = "category" | "label";

interface ColoringModeChoiceProps {
    readonly mode: ColoringMode;
    readonly onModeChange: (mode: ColoringMode) => void;
}

interface ModeChoice {
    readonly mode: ColoringMode;
    readonly label: string;
}

const CHOICES: readonly ModeChoice[] = [
    { mode: "category", label: "Category" },
    { mode: "label", label: "Labels" },
];

/** The two ways the cloud paints its samples, one pressed, the same control in the toolbar and in the legend's sheet. */
export function ColoringModeChoice({ mode, onModeChange }: ColoringModeChoiceProps): ReactElement {
    return (
        <>
            {CHOICES.map((choice) => (
                <button
                    key={choice.mode}
                    type="button"
                    aria-pressed={mode === choice.mode}
                    onClick={() => {
                        onModeChange(choice.mode);
                    }}
                >
                    {choice.label}
                </button>
            ))}
        </>
    );
}
