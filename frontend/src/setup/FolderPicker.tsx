import { type ReactElement, useEffect, useState } from "react";

import { type FolderListing, getFolder, getPlaces, type Place } from "../api/setup";
import { describeError } from "../shared/fetchState";
import { BottomSheet } from "../shared/overlay/BottomSheet";

interface FolderPickerProps {
    readonly title: string;
    /** The folder the picker opens on; the person's first place when there is none yet. */
    readonly initialPath: string | null;
    readonly onChoose: (path: string) => void;
    readonly onClose: () => void;
}

type ListingState =
    | { readonly status: "loading" }
    | { readonly status: "error"; readonly message: string }
    | { readonly status: "ready"; readonly listing: FolderListing };

function describeContents(listing: FolderListing): string {
    const parts = [
        listing.module_files > 0 ? `${String(listing.module_files)} modules` : null,
        listing.audio_files > 0 ? `${String(listing.audio_files)} audio files` : null,
    ].filter((part): part is string => part !== null);
    return parts.length > 0
        ? `This folder holds ${parts.join(" and ")}.`
        : "No modules or audio files sit directly in this folder.";
}

/**
 * A folder browser the local application serves, since a web page reads no folder names of its own:
 * the person's usual places and drives, the folders inside the one open, and how many modules and
 * audio files it holds, so a collection is recognized before it is chosen.
 */
export function FolderPicker({ title, initialPath, onChoose, onClose }: FolderPickerProps): ReactElement {
    const [places, setPlaces] = useState<readonly Place[]>([]);
    const [path, setPath] = useState<string | null>(initialPath);
    const [listing, setListing] = useState<ListingState>({ status: "loading" });

    useEffect(() => {
        let active = true;
        getPlaces()
            .then((found) => {
                if (!active) {
                    return;
                }
                setPlaces(found);
                setPath((current) => current ?? found[0]?.path ?? null);
            })
            .catch((error: unknown) => {
                if (active) {
                    setListing({ status: "error", message: describeError(error) });
                }
            });
        return (): void => {
            active = false;
        };
    }, []);

    useEffect(() => {
        if (path === null) {
            return undefined;
        }
        let active = true;
        setListing({ status: "loading" });
        getFolder(path)
            .then((found) => {
                if (active) {
                    setListing({ status: "ready", listing: found });
                }
            })
            .catch((error: unknown) => {
                if (active) {
                    setListing({ status: "error", message: describeError(error) });
                }
            });
        return (): void => {
            active = false;
        };
    }, [path]);

    return (
        <BottomSheet title={title} onClose={onClose}>
            <nav className="folder-places" aria-label="Places">
                {places.map((place) => (
                    <button
                        key={place.path}
                        type="button"
                        className="folder-place"
                        aria-pressed={place.path === path}
                        onClick={() => {
                            setPath(place.path);
                        }}
                    >
                        {place.name}
                    </button>
                ))}
            </nav>
            {listing.status === "loading" && <p className="folder-note">Opening the folder…</p>}
            {listing.status === "error" && (
                <p className="error-notice" role="alert">
                    {listing.message}
                </p>
            )}
            {listing.status === "ready" && (
                <>
                    <div className="folder-current">
                        <button
                            type="button"
                            className="folder-up"
                            disabled={listing.listing.parent === null}
                            onClick={() => {
                                setPath(listing.listing.parent);
                            }}
                        >
                            ↑ Up
                        </button>
                        <span className="folder-path mono">{listing.listing.path}</span>
                    </div>
                    <p className="folder-note">{describeContents(listing.listing)}</p>
                    <ul className="folder-list">
                        {listing.listing.folders.map((folder) => (
                            <li key={folder.path} className="folder-item">
                                <button
                                    type="button"
                                    className="folder-entry"
                                    onClick={() => {
                                        setPath(folder.path);
                                    }}
                                >
                                    <span aria-hidden>📁</span> {folder.name}
                                </button>
                            </li>
                        ))}
                        {listing.listing.folders.length === 0 && (
                            <li className="folder-item folder-note">No folders inside.</li>
                        )}
                    </ul>
                    <div className="setup-actions">
                        <button
                            type="button"
                            className="setup-button setup-button-primary"
                            onClick={() => {
                                onChoose(listing.listing.path);
                            }}
                        >
                            Choose this folder
                        </button>
                        <button type="button" className="setup-button" onClick={onClose}>
                            Cancel
                        </button>
                    </div>
                </>
            )}
        </BottomSheet>
    );
}
