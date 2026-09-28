from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from sampleextract.links.file import LinkFileRefused, read_link_rows

A_PAGE = "https://example.org/a"
ANOTHER_PAGE = "https://example.org/b"


@dataclass(frozen=True)
class RefusalCase:
    name: str
    text: str
    lines: tuple[int, ...]


REFUSALS = (
    RefusalCase("an empty file", "", ()),
    RefusalCase("a header naming one column", f"location\nXM/a.xm\n", ()),
    RefusalCase("an absolute location", f"location,link\n/XM/a.xm,{A_PAGE}\n", (2,)),
    RefusalCase("an empty location", f"location,link\n,{A_PAGE}\n", (2,)),
    RefusalCase("a location climbing out", f"location,link\n../a.xm,{A_PAGE}\n", (2,)),
    RefusalCase("a location with a backslash", f"location,link\nXM\\a.xm,{A_PAGE}\n", (2,)),
    RefusalCase("a link off the web", "location,link\nXM/a.xm,ftp://example.org/a\n", (2,)),
    RefusalCase("a link without a host", "location,link\nXM/a.xm,https:///a\n", (2,)),
    RefusalCase(
        "a location named twice",
        f"location,link\nXM/a.xm,{A_PAGE}\nXM/b.xm,{ANOTHER_PAGE}\nXM/a.xm,{ANOTHER_PAGE}\n",
        (2, 4),
    ),
    RefusalCase(
        "two bad rows",
        f"location,link\n/XM/a.xm,{A_PAGE}\nXM/b.xm,{ANOTHER_PAGE}\nXM/c.xm,mailto:c\n",
        (2, 4),
    ),
)


def _file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "links.csv"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("case", REFUSALS, ids=lambda case: case.name)
def test_a_file_with_a_problem_is_refused_whole_naming_every_line(tmp_path: Path, case: RefusalCase) -> None:
    path = _file(tmp_path, case.text)

    with pytest.raises(LinkFileRefused) as raised:
        read_link_rows(path)

    problem = str(raised.value).replace(str(path), "")
    for line in case.lines:
        assert re.search(rf"\b{line}\b", problem), problem


def test_rows_carry_their_location_link_and_line(tmp_path: Path) -> None:
    rows = read_link_rows(_file(tmp_path, f"location,link\nXM/a.xm,{A_PAGE}\n\nIT/b.it,{ANOTHER_PAGE}\n"))

    assert [(row.location, row.link, row.line_number) for row in rows] == [
        ("XM/a.xm", A_PAGE, 2),
        ("IT/b.it", ANOTHER_PAGE, 4),
    ]


def test_columns_are_read_by_name_beside_any_others(tmp_path: Path) -> None:
    rows = read_link_rows(_file(tmp_path, f"title,link,location\nA song,{A_PAGE},XM/a.xm\n"))

    assert [(row.location, row.link) for row in rows] == [("XM/a.xm", A_PAGE)]


def test_a_quoted_location_keeps_its_comma(tmp_path: Path) -> None:
    rows = read_link_rows(_file(tmp_path, f'location,link\n"XM/Artist - Title, part 2.xm",{A_PAGE}\n'))

    assert rows[0].location == "XM/Artist - Title, part 2.xm"


def test_a_file_a_spreadsheet_saved_reads_past_its_byte_order_mark(tmp_path: Path) -> None:
    path = tmp_path / "links.csv"
    path.write_bytes(f"location,link\r\nXM/a.xm,{A_PAGE}\r\n".encode("utf-8-sig"))

    assert read_link_rows(path)[0].location == "XM/a.xm"


def test_a_file_that_is_not_there_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LinkFileRefused):
        read_link_rows(tmp_path / "absent.csv")
