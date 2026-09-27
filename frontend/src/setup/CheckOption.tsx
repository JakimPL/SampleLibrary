import { type ReactElement, type ReactNode, useId } from "react";

interface CheckOptionProps {
    readonly title: string;
    readonly note: string;
    readonly checked: boolean;
    readonly disabled: boolean;
    readonly onChange: (checked: boolean) => void;
    /** Whatever stands under the note, such as the address a switch opens. */
    readonly children?: ReactNode;
}

/** A switch with its title beside it and a note under the title, the note describing the switch to a screen reader too. */
export function CheckOption({ title, note, checked, disabled, onChange, children }: CheckOptionProps): ReactElement {
    const inputId = useId();
    const noteId = useId();
    return (
        <div className="check-option">
            <input
                id={inputId}
                type="checkbox"
                className="check"
                aria-describedby={noteId}
                checked={checked}
                disabled={disabled}
                onChange={(event) => {
                    onChange(event.target.checked);
                }}
            />
            <span className="check-option-text">
                <label htmlFor={inputId} className="check-option-title">
                    {title}
                </label>
                <span id={noteId} className="setup-hint">
                    {note}
                </span>
                {children}
            </span>
        </div>
    );
}
