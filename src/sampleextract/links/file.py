from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ValidationError, field_validator

from samplecore.models.base import FROZEN
from samplecore.models.module_link import PageUrl
from samplecore.models.sample_file import below_the_directory
from sampleextract.links.messages import COLUMN_MISSING, NO_HEADER, REPEATED_LOCATION, ROW_REFUSED

LOCATION_COLUMN: Final[str] = "location"
LINK_COLUMN: Final[str] = "link"
COLUMNS: Final[tuple[str, ...]] = (LOCATION_COLUMN, LINK_COLUMN)
# A file a spreadsheet saved opens with a byte-order mark, which this encoding reads past.
FILE_ENCODING: Final[str] = "utf-8-sig"
PROBLEM_SEPARATOR: Final[str] = "; "


class LinkFileRefused(ValueError):
    """Raised when a links file cannot be read as the list of module locations and page links it stands for."""


class LinkRow(BaseModel):
    """One row of a links file: where a module file sits under the collection, and the page it came from."""

    model_config = FROZEN

    location: str
    link: PageUrl
    line_number: int

    @field_validator("location")
    @classmethod
    def _under_the_collection(cls, location: str) -> str:
        if "\\" in location:
            raise ValueError(f"{location!r} must be written with forward slashes")
        return below_the_directory(location)


def read_link_rows(path: Path) -> tuple[LinkRow, ...]:
    """Every row of a links file, checked whole before any of them is acted on.

    Every problem the file holds is named at once, so a person fixes the file in one pass.

    Raises:
        LinkFileRefused: the file cannot be read, its header lacks a column, a row names no
            location under the collection or no web page, or one location is named twice.
    """
    try:
        with path.open(encoding=FILE_ENCODING, newline="") as file:
            return _rows_of(csv.DictReader(file), path)
    except OSError as error:
        raise LinkFileRefused(f"{path} cannot be read ({error.strerror})") from error
    except UnicodeDecodeError as error:
        raise LinkFileRefused(f"{path} cannot be read ({error})") from error


def _rows_of(reader: csv.DictReader[str], path: Path) -> tuple[LinkRow, ...]:
    """The rows a reader over the file yields, once its header names both columns.

    Raises:
        LinkFileRefused: the header is missing or lacks a column, a row is refused, or a location repeats.
    """
    fieldnames = reader.fieldnames
    if fieldnames is None:
        raise LinkFileRefused(NO_HEADER.format(path=path))
    missing = [column for column in COLUMNS if column not in fieldnames]
    if missing:
        raise LinkFileRefused(
            PROBLEM_SEPARATOR.join(COLUMN_MISSING.format(path=path, column=column) for column in missing)
        )

    problems: list[str] = []
    rows: list[LinkRow] = []
    lines_by_location: dict[str, list[int]] = defaultdict(list)
    for record in reader:
        line_number = reader.line_num
        try:
            row = LinkRow(
                location=record[LOCATION_COLUMN] or "", link=record[LINK_COLUMN] or "", line_number=line_number
            )
        except ValidationError as error:
            problems.append(ROW_REFUSED.format(line=line_number, path=path, problem=error.errors()[0]["msg"]))
            continue
        lines_by_location[row.location].append(line_number)
        rows.append(row)
    problems.extend(
        REPEATED_LOCATION.format(path=path, location=location, lines=", ".join(str(line) for line in lines))
        for location, lines in sorted(lines_by_location.items())
        if len(lines) > 1
    )
    if problems:
        raise LinkFileRefused(PROBLEM_SEPARATOR.join(problems))
    return tuple(rows)
