from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection

from samplecore.storage.repositories.module_link import PostgresModuleLinkRepository
from sampleextract.links.file import LinkFileRefused
from sampleextract.links.importing import import_links
from tests.sampleextract.links.conftest import catalog_module_file, write_links

A_PAGE = "https://www.modules.pl/?id=module&mod=1"
ANOTHER_PAGE = "https://www.modules.pl/?id=module&mod=2"
A_THIRD_PAGE = "https://modarchive.org/index.php?request=view_by_moduleid&query=3"


def test_a_row_links_the_module_its_file_hashes_to(
    connection: Connection, collection: Path, tmp_path: Path, xm_module_bytes: bytes
) -> None:
    module = catalog_module_file(connection, collection, "XM/song.xm", xm_module_bytes)
    path = write_links(tmp_path / "links.csv", (("XM/song.xm", A_PAGE),))

    summary = import_links(connection, path=path, source_directory=collection)

    assert (summary.recorded, summary.missing, summary.uncataloged) == (1, (), ())
    assert PostgresModuleLinkRepository(connection).get_many([module.hash])[module.hash].url == A_PAGE


def test_a_copy_under_another_name_links_the_same_module(
    connection: Connection, collection: Path, tmp_path: Path, xm_module_bytes: bytes
) -> None:
    module = catalog_module_file(connection, collection, "XM/song.xm", xm_module_bytes)
    (collection / "XM" / "copy of song.xm").write_bytes(xm_module_bytes)
    path = write_links(tmp_path / "links.csv", (("XM/copy of song.xm", A_PAGE),))

    summary = import_links(connection, path=path, source_directory=collection)

    assert summary.recorded == 1
    assert PostgresModuleLinkRepository(connection).get_many([module.hash])[module.hash].url == A_PAGE


def test_a_missing_file_and_an_uncataloged_one_are_passed_over_and_counted(
    connection: Connection, collection: Path, tmp_path: Path, xm_module_bytes: bytes
) -> None:
    catalog_module_file(connection, collection, "XM/song.xm", xm_module_bytes)
    (collection / "XM" / "stranger.xm").write_bytes(b"not a cataloged module")
    path = write_links(
        tmp_path / "links.csv",
        (("XM/absent.xm", A_PAGE), ("XM/stranger.xm", ANOTHER_PAGE), ("XM/song.xm", A_THIRD_PAGE)),
    )

    summary = import_links(connection, path=path, source_directory=collection)

    assert summary.recorded == 1
    assert summary.missing == ("XM/absent.xm",)
    assert summary.uncataloged == ("XM/stranger.xm",)
    assert PostgresModuleLinkRepository(connection).count() == 1


def test_a_second_import_replaces_the_links_it_names_and_keeps_the_others(
    connection: Connection, collection: Path, tmp_path: Path, xm_module_bytes: bytes, it_module_bytes: bytes
) -> None:
    first = catalog_module_file(connection, collection, "XM/song.xm", xm_module_bytes)
    second = catalog_module_file(connection, collection, "IT/song.it", it_module_bytes)
    import_links(
        connection,
        path=write_links(tmp_path / "first.csv", (("XM/song.xm", A_PAGE), ("IT/song.it", ANOTHER_PAGE))),
        source_directory=collection,
    )

    import_links(
        connection,
        path=write_links(tmp_path / "second.csv", (("XM/song.xm", A_THIRD_PAGE),)),
        source_directory=collection,
    )

    links = PostgresModuleLinkRepository(connection).get_many([first.hash, second.hash])
    assert (links[first.hash].url, links[second.hash].url) == (A_THIRD_PAGE, ANOTHER_PAGE)


def test_two_rows_holding_one_module_under_two_links_refuse_the_file(
    connection: Connection, collection: Path, tmp_path: Path, xm_module_bytes: bytes
) -> None:
    catalog_module_file(connection, collection, "XM/song.xm", xm_module_bytes)
    (collection / "XM" / "copy.xm").write_bytes(xm_module_bytes)
    path = write_links(tmp_path / "links.csv", (("XM/song.xm", A_PAGE), ("XM/copy.xm", ANOTHER_PAGE)))

    with pytest.raises(LinkFileRefused, match="XM/copy.xm"):
        import_links(connection, path=path, source_directory=collection)

    assert PostgresModuleLinkRepository(connection).count() == 0


def test_two_rows_holding_one_module_under_one_link_record_it_once(
    connection: Connection, collection: Path, tmp_path: Path, xm_module_bytes: bytes
) -> None:
    catalog_module_file(connection, collection, "XM/song.xm", xm_module_bytes)
    (collection / "XM" / "copy.xm").write_bytes(xm_module_bytes)
    path = write_links(tmp_path / "links.csv", (("XM/song.xm", A_PAGE), ("XM/copy.xm", A_PAGE)))

    summary = import_links(connection, path=path, source_directory=collection)

    assert summary.recorded == 1
    assert PostgresModuleLinkRepository(connection).count() == 1


def test_a_refused_file_writes_nothing(
    connection: Connection, collection: Path, tmp_path: Path, xm_module_bytes: bytes
) -> None:
    catalog_module_file(connection, collection, "XM/song.xm", xm_module_bytes)
    path = write_links(tmp_path / "links.csv", (("XM/song.xm", A_PAGE), ("/XM/song.xm", ANOTHER_PAGE)))

    with pytest.raises(LinkFileRefused):
        import_links(connection, path=path, source_directory=collection)

    assert PostgresModuleLinkRepository(connection).count() == 0
