from __future__ import annotations

import logging
from collections.abc import Iterable
from http import HTTPStatus
from pathlib import Path

from fastapi import HTTPException

from samplecore.models.sample_file import SampleFile
from samplecore.storage.sample_audio import SampleUnavailableError
from sampleserver.messages import UNREADABLE_AUDIO
from sampleserver.policy import ServingPolicy

_logger = logging.getLogger(__name__)


def files_inside(sample_files: Iterable[SampleFile], directories: tuple[Path, ...]) -> tuple[SampleFile, ...]:
    """The files among ``sample_files`` found in one of ``directories``, which are the only files a server opens.

    The catalog names a file by the folder it was scanned under, and a served library reads the
    folders its own configuration lists; a file found anywhere else stays closed, whatever the
    catalog it serves says about it.
    """
    return tuple(found for found in sample_files if found.location.directory in directories)


def unreadable_audio(error: SampleUnavailableError, policy: ServingPolicy) -> HTTPException:
    """The 404 for a sample none of whose files reads as it was scanned, naming the file where the policy names internals."""
    _logger.warning("%s", error)
    return HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=policy.refusal(str(error), plain=UNREADABLE_AUDIO))
