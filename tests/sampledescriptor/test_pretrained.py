from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from samplecore.config import LibraryConfig
from samplecore.hashing import file_sha256
from sampledescriptor import pretrained
from sampledescriptor.commands import adopt
from sampledescriptor.descriptors.learned import DescriptorDescription
from sampledescriptor.model_paths import descriptor_path
from sampledescriptor.pretrained import (
    PretrainedDescriptorMissingError,
    PretrainedDownloadError,
    PretrainedRelease,
    download_pretrained,
    read_pretrained_release,
    write_pretrained_release,
)
from sampledescriptor.releasing import release_of


@pytest.fixture(name="release")
def fixture_release(stored_descriptor: Path) -> PretrainedRelease:
    """The tiny descriptor's release, published at a file URL the download reads like any other."""
    return release_of(stored_descriptor, url=stored_descriptor.as_uri())


@pytest.fixture(name="published")
def fixture_published(tmp_path: Path, release: PretrainedRelease, monkeypatch: pytest.MonkeyPatch) -> PretrainedRelease:
    """The installation's release record, naming the tiny descriptor."""
    path = tmp_path / "pretrained.toml"
    write_pretrained_release(release, path)
    monkeypatch.setattr(pretrained, "PRETRAINED_RELEASE_PATH", path)
    return release


def test_a_release_names_the_descriptors_bytes_and_the_grid_it_was_trained_on(
    stored_descriptor: Path, release: PretrainedRelease, descriptor_description: DescriptorDescription
) -> None:
    assert release.sha256 == file_sha256(stored_descriptor)
    assert release.grid.canonicalizer == descriptor_description.canonicalizer
    assert release.grid.anchor == descriptor_description.geometry.anchor
    assert release.grid.bands_per_semitone == descriptor_description.bands_per_semitone


def test_a_release_record_reads_back_as_it_was_written(tmp_path: Path, release: PretrainedRelease) -> None:
    path = tmp_path / "pretrained.toml"

    write_pretrained_release(release, path)

    assert read_pretrained_release(path) == release


def test_a_version_without_a_published_descriptor_says_how_to_publish_one(tmp_path: Path) -> None:
    with pytest.raises(PretrainedDescriptorMissingError, match="release-descriptor"):
        read_pretrained_release(tmp_path / "missing.toml")


def test_adopting_downloads_the_published_descriptor_into_the_library(
    tmp_path: Path, stored_descriptor: Path, published: PretrainedRelease  # pylint: disable=unused-argument
) -> None:
    config = LibraryConfig(library_root=tmp_path / "library")

    adopt.run(config, argparse.Namespace(descriptor="descriptor-run-abc"))

    adopted = descriptor_path(config.library_root, name="descriptor-run-abc")
    assert file_sha256(adopted) == file_sha256(stored_descriptor)


def test_a_download_differing_from_its_release_is_refused_and_leaves_nothing_behind(
    tmp_path: Path, release: PretrainedRelease
) -> None:
    target = tmp_path / "library" / "descriptor.pt"

    with pytest.raises(PretrainedDownloadError, match="doesn't match"):
        download_pretrained(release.model_copy(update={"sha256": "0" * 64}), target)

    assert not any(target.parent.iterdir())


def test_a_release_that_fails_to_download_is_refused(tmp_path: Path, release: PretrainedRelease) -> None:
    missing = release.model_copy(update={"url": (tmp_path / "missing.pt").as_uri()})

    with pytest.raises(PretrainedDownloadError, match="Couldn't download"):
        download_pretrained(missing, tmp_path / "library" / "descriptor.pt")
