from __future__ import annotations

from pathlib import Path

import pytest

from samplemorph.registries import PGHI_VOCODER_NAME, RESTORED_VOCODER_NAME
from samplemorph.vocoders.pghi import PghiVocoder
from samplemorph.vocoders.restored import DEFAULT_RESTORER_NAME
from samplemorph.vocoders.selection import vocoder_named


def test_a_name_alone_builds_the_integrating_vocoder(tmp_path: Path) -> None:
    vocoder = vocoder_named(PGHI_VOCODER_NAME, library_root=tmp_path, restorer_name=DEFAULT_RESTORER_NAME, device="cpu")

    assert isinstance(vocoder, PghiVocoder)


def test_the_restored_vocoder_reports_a_missing_restorer_by_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no restorer is stored"):
        vocoder_named(RESTORED_VOCODER_NAME, library_root=tmp_path, restorer_name="absent", device="cpu")
