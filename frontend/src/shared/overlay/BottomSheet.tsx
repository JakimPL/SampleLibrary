import type { ReactElement, ReactNode } from "react";
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

interface BottomSheetProps {
    readonly title: string;
    readonly onClose: () => void;
    readonly children: ReactNode;
}

const CLOSE_KEY = "Escape";

/**
 * A panel that rises from the bottom edge over everything else, closed by the scrim behind it or
 * by Escape. It takes the focus while open and hands it back to the control that opened it, and
 * it renders at the document's root, so the rows and panels beneath cannot clip or shift it.
 */
export function BottomSheet({ title, onClose, children }: BottomSheetProps): ReactElement {
    const sheetRef = useRef<HTMLDivElement | null>(null);
    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;

    useEffect(() => {
        const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        sheetRef.current?.focus();
        function handleKeyDown(event: KeyboardEvent): void {
            if (event.key === CLOSE_KEY) {
                onCloseRef.current();
            }
        }
        document.addEventListener("keydown", handleKeyDown);
        return (): void => {
            document.removeEventListener("keydown", handleKeyDown);
            opener?.focus();
        };
    }, []);

    return createPortal(
        <div className="sheet-layer">
            <button type="button" className="sheet-scrim" aria-label="Close" onClick={onClose} />
            <div ref={sheetRef} className="sheet" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}>
                <div className="sheet-handle" aria-hidden />
                <h2 className="sheet-title">{title}</h2>
                <div className="sheet-body">{children}</div>
            </div>
        </div>,
        document.body,
    );
}
