from __future__ import annotations

from typing import Final

# What `sampleripper links import` tells the person importing, each a sentence of its own.

NO_SOURCE_DIRECTORY: Final[str] = (
    "No module_source_directory is configured; set it to your module collection, which the file's "
    "locations are read under."
)
SOURCE_DIRECTORY_MISSING: Final[str] = "{problem}; set module_source_directory to your module collection."
IMPORTED_NOTHING: Final[str] = "Imported nothing: {problem}."
NO_HEADER: Final[str] = "{path} holds no header row; its first line names the columns, location and link"
COLUMN_MISSING: Final[str] = "{path} names no {column} column; its header names both location and link"
ROW_REFUSED: Final[str] = "line {line} of {path}: {problem}"
REPEATED_LOCATION: Final[str] = "{path} names {location} on lines {lines}"
CONFLICTING_LINKS: Final[str] = "{first} and {second} hold one module ({module_hash}) under two links"
FILE_MISSING: Final[str] = "Skipped {location}: its file is missing or cannot be read."
NOT_CATALOGED: Final[str] = "Skipped {location}: no cataloged module holds its bytes."
MORE_SKIPPED: Final[str] = "... and {count} more."
RECORDED: Final[str] = (
    "Recorded {recorded} link(s) from {path}: {missing} file(s) missing, {uncataloged} not cataloged."
)
