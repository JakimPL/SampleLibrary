import type { ReactElement, ReactNode } from "react";

import { BottomSheet } from "./BottomSheet";

export interface SheetAction {
    readonly id: string;
    readonly label: string;
    readonly disabled: boolean;
    readonly run: () => void;
}

interface ActionSheetProps {
    readonly title: string;
    /** Whatever stands above the actions, such as a row of stars. */
    readonly children: ReactNode;
    readonly actions: readonly SheetAction[];
    readonly onClose: () => void;
}

/** A bottom sheet of named actions, each closing the sheet once it has run. */
export function ActionSheet({ title, children, actions, onClose }: ActionSheetProps): ReactElement {
    return (
        <BottomSheet title={title} onClose={onClose}>
            {children}
            <div className="sheet-actions">
                {actions.map((action) => (
                    <button
                        key={action.id}
                        type="button"
                        disabled={action.disabled}
                        onClick={() => {
                            action.run();
                            onClose();
                        }}
                    >
                        {action.label}
                    </button>
                ))}
            </div>
        </BottomSheet>
    );
}
