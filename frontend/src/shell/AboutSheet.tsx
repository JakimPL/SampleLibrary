import type { ReactElement } from "react";

import { buttonClassName } from "../shared/controls/buttonClassName";
import { Icon } from "../shared/icons/Icon";
import { BottomSheet } from "../shared/overlay/BottomSheet";
import { APP_VERSION } from "../version";

interface AboutSheetProps {
    readonly onClose: () => void;
}

export const ABOUT_TITLE = "About";
const APP_NAME = "SampleRipper";
const DESCRIPTION = "Browse, audition, label and morph the samples of a tracker module library.";
const AUTHOR_LINE = "Made by Jakim / Stage Magician";
const REPOSITORY_URL = "https://github.com/JakimPL/SampleRipper";
const REPOSITORY_LABEL = "Source on GitHub";
const LOGO_PATH = "/favicon.svg";
const LOGO_SIZE_PX = 96;

/**
 * What the app is, in one sheet: its logo, name and version, a line on what it does, who made it,
 * and the way to its source. The version is the one the web app was built with, so a person can
 * copy it into a bug report; the link opens in a new tab and says so with its glyph.
 */
export function AboutSheet({ onClose }: AboutSheetProps): ReactElement {
    return (
        <BottomSheet title={ABOUT_TITLE} onClose={onClose}>
            <div className="about">
                <img className="about-logo" src={LOGO_PATH} alt="" width={LOGO_SIZE_PX} height={LOGO_SIZE_PX} />
                <h3 className="about-name">{APP_NAME}</h3>
                <p className="about-version">Version {APP_VERSION}</p>
                <p className="about-description">{DESCRIPTION}</p>
                <p className="about-author">{AUTHOR_LINE}</p>
                <a
                    className={buttonClassName({ variant: "secondary", className: "about-link" })}
                    href={REPOSITORY_URL}
                    target="_blank"
                    rel="noreferrer"
                >
                    {REPOSITORY_LABEL}
                    <Icon name="external" label={null} />
                </a>
            </div>
        </BottomSheet>
    );
}
