from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from samplecore.digests import DigestValue, digest_of_rows, stat_digest


@dataclass(frozen=True)
class DistinctRowsCase:
    name: str
    first: tuple[tuple[DigestValue, ...], ...]
    second: tuple[tuple[DigestValue, ...], ...]


@pytest.mark.parametrize(
    "case",
    [
        DistinctRowsCase("values running together", (("a,b",),), (("a", "b"),)),
        DistinctRowsCase("a row boundary", (("a", "b"),), (("a",), ("b",))),
        DistinctRowsCase("a number beside its text", ((44100,),), (("44100",),)),
        DistinctRowsCase("nothing beside an empty text", ((None,),), (("",),)),
        DistinctRowsCase("composed and decomposed accents", (("r\u00e9sum\u00e9",),), (("re\u0301sume\u0301",),)),
        DistinctRowsCase("no rows beside one empty row", (), ((),)),
    ],
    ids=lambda case: case.name,
)
def test_rows_that_differ_digest_apart(case: DistinctRowsCase) -> None:
    assert digest_of_rows(case.first) != digest_of_rows(case.second)


def test_the_same_rows_digest_alike_however_they_arrive() -> None:
    rows = [("a" * 64, 44100), ("b" * 64, None)]

    assert digest_of_rows(rows) == digest_of_rows(tuple(rows))
    assert digest_of_rows(rows) == digest_of_rows(iter(rows))


@pytest.fixture(name="collection")
def fixture_collection(tmp_path: Path) -> Path:
    root = tmp_path / "collection"
    (root / "Drums").mkdir(parents=True)
    (root / "Drums" / "kick.xm").write_bytes(b"kick")
    (root / "song.it").write_bytes(b"song")
    return root


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def test_a_collection_listed_again_unchanged_digests_alike(collection: Path) -> None:
    assert stat_digest(collection, _files(collection)) == stat_digest(collection, list(reversed(_files(collection))))


def test_a_collection_moved_under_another_root_keeps_its_digest(collection: Path, tmp_path: Path) -> None:
    before = stat_digest(collection, _files(collection))
    moved = collection.rename(tmp_path / "moved")

    assert stat_digest(moved, _files(moved)) == before


@dataclass(frozen=True)
class CollectionChangeCase:
    name: str
    change: str


@pytest.mark.parametrize(
    "case",
    [
        CollectionChangeCase("a file added", "add"),
        CollectionChangeCase("a file removed", "remove"),
        CollectionChangeCase("a file renamed", "rename"),
        CollectionChangeCase("a file written again", "rewrite"),
        CollectionChangeCase("a file's write time moved", "touch"),
    ],
    ids=lambda case: case.name,
)
def test_every_change_to_a_collection_moves_its_digest(collection: Path, case: CollectionChangeCase) -> None:
    before = stat_digest(collection, _files(collection))
    kick = collection / "Drums" / "kick.xm"
    match case.change:
        case "add":
            (collection / "new.mod").write_bytes(b"new")
        case "remove":
            kick.unlink()
        case "rename":
            kick.rename(collection / "Drums" / "kick-01.xm")
        case "rewrite":
            kick.write_bytes(b"kick, longer")
        case "touch":
            status = kick.stat()
            os.utime(kick, ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000_000))

    assert stat_digest(collection, _files(collection)) != before


def test_a_file_gone_between_the_listing_and_the_digest_moves_it(collection: Path) -> None:
    listed = _files(collection)
    before = stat_digest(collection, listed)
    (collection / "song.it").unlink()

    assert stat_digest(collection, listed) != before
