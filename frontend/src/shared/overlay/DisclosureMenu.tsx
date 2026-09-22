import type { MouseEvent, ReactElement, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import { classNames } from "../classNames";

interface DisclosureMenuProps {
    readonly label: string;
    readonly className: string;
    readonly children: ReactNode;
}

/**
 * A button that drops a small panel beneath it and takes it away again on a second click, on
 * Escape, or on a press anywhere outside. Built on `<details>`, so the open state is the
 * element's own and a screen reader hears a disclosure.
 */
export function DisclosureMenu({ label, className, children }: DisclosureMenuProps): ReactElement {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDetailsElement | null>(null);

    useEffect(() => {
        if (!open) {
            return undefined;
        }
        function handlePointerDown(event: PointerEvent): void {
            const root = rootRef.current;
            if (root !== null && event.target instanceof Node && !root.contains(event.target)) {
                setOpen(false);
            }
        }
        function handleKeyDown(event: KeyboardEvent): void {
            if (event.key === "Escape") {
                setOpen(false);
            }
        }
        document.addEventListener("pointerdown", handlePointerDown);
        document.addEventListener("keydown", handleKeyDown);
        return (): void => {
            document.removeEventListener("pointerdown", handlePointerDown);
            document.removeEventListener("keydown", handleKeyDown);
        };
    }, [open]);

    function handleSummaryClick(event: MouseEvent<HTMLElement>): void {
        event.preventDefault();
        setOpen((current) => !current);
    }

    return (
        <details ref={rootRef} className={classNames("disclosure-menu", className)} open={open}>
            <summary className="disclosure-menu-summary" onClick={handleSummaryClick}>
                {label}
            </summary>
            <div className="disclosure-menu-panel">{children}</div>
        </details>
    );
}
