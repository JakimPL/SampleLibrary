import type { ReactElement } from "react";

import type { InputMode } from "../layout/layoutMode";
import { BottomSheet } from "../shared/overlay/BottomSheet";

interface GuideEntry {
    readonly gesture: string;
    readonly meaning: string;
}

interface GuideSection {
    readonly title: string;
    readonly entries: readonly GuideEntry[];
}

const TOUCH_GUIDE: readonly GuideSection[] = [
    {
        title: "Lists",
        entries: [
            { gesture: "Tap a row", meaning: "takes the sample in hand and plays it" },
            { gesture: "Hold a row", meaning: "opens its stars, heart and label" },
            { gesture: "Tap ›", meaning: "opens the sample or module as a page" },
            { gesture: "Tap the heart", meaning: "keeps the sample close" },
        ],
    },
    {
        title: "The tray",
        entries: [
            { gesture: "Tap the waveform", meaning: "plays or pauses the sample in hand" },
            { gesture: "Tap a star or the heart", meaning: "rates the sample in hand, or keeps it close" },
        ],
    },
    {
        title: "A page",
        entries: [
            { gesture: "Tap ‹ or ›", meaning: "walks the listing one sample at a time" },
            { gesture: "Tap ←", meaning: "returns to the list" },
        ],
    },
    {
        title: "The cloud",
        entries: [
            { gesture: "Tap a point", meaning: "takes it in hand and plays it" },
            { gesture: "Tap empty space", meaning: "lets go of the point in hand" },
            { gesture: "Drag", meaning: "moves the cloud" },
            { gesture: "Pinch", meaning: "zooms about the fingers" },
            { gesture: "Hold a point", meaning: "opens its actions" },
            {
                gesture: "A or B under the cloud",
                meaning: "plays that end and selects it: every sample tapped next becomes it, until it is tapped again",
            },
            { gesture: "× beside A or B", meaning: "lets that end go" },
            { gesture: "⇄", meaning: "swaps the ends and mirrors the weight" },
            { gesture: "The waveform button", meaning: "hides and shows the morph's slider and waveform" },
            { gesture: "⌖", meaning: "centers the cloud on the point in hand" },
        ],
    },
];

const POINTER_GUIDE: readonly GuideSection[] = [
    {
        title: "Lists",
        entries: [
            { gesture: "Click a row", meaning: "takes the sample in hand" },
            { gesture: "Double-click, or Enter on the name", meaning: "opens the sample or module" },
            { gesture: "Shift-click", meaning: "joins the sample to the one in hand as a morph pair" },
            { gesture: "↑ ↓", meaning: "move between rows" },
            { gesture: "Space", meaning: "plays the sample" },
            { gesture: "F", meaning: "keeps the sample close" },
            { gesture: "1 to 5", meaning: "rate the sample" },
            { gesture: "M", meaning: "joins the sample to the one in hand as a morph pair" },
        ],
    },
    {
        title: "The open sample",
        entries: [{ gesture: "Alt+← Alt+→", meaning: "step through the listing" }],
    },
    {
        title: "The cloud",
        entries: [
            { gesture: "Click a point", meaning: "takes it in hand and plays it" },
            { gesture: "Double-click a point", meaning: "opens it" },
            { gesture: "Drag, scroll", meaning: "move and zoom the cloud" },
            { gesture: "Right-click a point", meaning: "joins it to the sample in hand as a morph pair" },
            { gesture: "Right-drag between two points", meaning: "makes them a morph pair" },
            {
                gesture: "A or B under the cloud",
                meaning:
                    "plays that end and selects it: every sample clicked next becomes it, until it is clicked again",
            },
            { gesture: "× beside A or B", meaning: "lets that end go" },
            { gesture: "⇄", meaning: "swaps the ends and mirrors the weight" },
            { gesture: "The waveform button", meaning: "hides and shows the morph's slider and waveform" },
            { gesture: "Escape", meaning: "lets go of the point in hand" },
        ],
    },
];

const TITLES: Readonly<Record<InputMode, string>> = { touch: "Gestures", pointer: "Keyboard and mouse" };

interface GuideSheetProps {
    readonly input: InputMode;
    readonly onClose: () => void;
}

/** What each gesture, click and key does, worded for the input the person has. */
export function GuideSheet({ input, onClose }: GuideSheetProps): ReactElement {
    const sections = input === "touch" ? TOUCH_GUIDE : POINTER_GUIDE;
    return (
        <BottomSheet title={TITLES[input]} onClose={onClose}>
            {sections.map((section) => (
                <section key={section.title} className="guide-section">
                    <h3 className="guide-title">{section.title}</h3>
                    <dl className="guide">
                        {section.entries.map((entry) => (
                            <div key={entry.gesture} className="guide-entry">
                                <dt className="guide-gesture">{entry.gesture}</dt>
                                <dd className="guide-meaning">{entry.meaning}</dd>
                            </div>
                        ))}
                    </dl>
                </section>
            ))}
        </BottomSheet>
    );
}

export const GUIDE_TITLES = TITLES;
