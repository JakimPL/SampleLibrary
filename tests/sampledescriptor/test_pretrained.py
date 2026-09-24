from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from samplecore.config import LibraryConfig
from samplecore.hashing import file_sha256
from sampledescriptor import pretrained
from sampledescriptor.bundling import bundle_descriptor
from sampledescriptor.commands import adopt
from sampledescriptor.descriptors.learned import DescriptorDescription
from sampledescriptor.model_paths import descriptor_path
from sampledescriptor.pretrained import PretrainedDescriptorMissingError, read_pretrained


@pytest.fixture
def bundle(tmp_path: Path, stored_descriptor: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The installation's bundle directory, holding the tiny descriptor."""
    directory = tmp_path / "bundle"
    bundle_descriptor(stored_descriptor, directory)
    monkeypatch.setattr(pretrained, "PRETRAINED_DIRECTORY", directory)
    return directory


def test_a_bundled_descriptor_names_the_grid_it_was_trained_on(
    stored_descriptor: Path, bundle: Path, descriptor_description: DescriptorDescription
) -> None:
    bundled = read_pretrained(bundle)

    assert bundled.manifest.canonicalizer == descriptor_description.canonicalizer
    assert bundled.manifest.anchor == descriptor_description.geometry.anchor
    assert bundled.manifest.bands_per_semitone == descriptor_description.bands_per_semitone
    assert bundled.content == file_sha256(stored_descriptor)


def test_an_installation_without_a_bundle_says_how_to_make_one(tmp_path: Path) -> None:
    with pytest.raises(PretrainedDescriptorMissingError, match="bundle-descriptor"):
        read_pretrained(tmp_path / "empty")


def test_adopting_stores_the_bundled_descriptor_in_the_library(
    tmp_path: Path, stored_descriptor: Path, bundle: Path  # pylint: disable=unused-argument
) -> None:
    config = LibraryConfig(library_root=tmp_path / "library")

    adopt.run(config, argparse.Namespace(descriptor="descriptor-run-abc"))

    adopted = descriptor_path(config.library_root, name="descriptor-run-abc")
    assert file_sha256(adopted) == file_sha256(stored_descriptor)
