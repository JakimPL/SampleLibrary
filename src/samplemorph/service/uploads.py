from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import IO

import numpy as np
import soundfile
from numpy.typing import NDArray


class UploadTooLargeError(ValueError):
    """Raised when an upload runs past the bytes one request may carry."""


class UploadUnreadableError(ValueError):
    """Raised when uploaded bytes hold no audio this process decodes."""


@dataclass(frozen=True)
class UploadedSound:
    """One sound a caller sent: its frames, the rate its file states, and a digest naming its bytes.

    The digest names the sound by what was sent, so the same file sent twice is one sound whatever
    it was called on the caller's side. Shape: `pcm` is ``(frames, channels)``.
    """

    pcm: NDArray[np.float64]
    rate_hz: float
    digest: str

    @property
    def frame_count(self) -> int:
        return int(self.pcm.shape[0])


def decode_upload(stream: IO[bytes], *, byte_limit: int) -> UploadedSound:
    """The sound an uploaded audio file holds, read in whole up to `byte_limit` bytes.

    Raises:
        UploadTooLargeError: the upload runs past `byte_limit` bytes.
        UploadUnreadableError: the bytes decode to no audio, to no frames, or to samples that are
            not finite.
    """
    data = stream.read(byte_limit + 1)
    if len(data) > byte_limit:
        raise UploadTooLargeError(f"an upload carries at most {byte_limit} bytes")
    try:
        pcm, rate = soundfile.read(io.BytesIO(data), dtype="float64", always_2d=True)
    except soundfile.LibsndfileError as error:
        raise UploadUnreadableError(f"the upload holds no audio this process decodes ({error})") from error
    frames: NDArray[np.float64] = pcm
    if frames.shape[0] == 0:
        raise UploadUnreadableError("the upload holds no frames")
    if not np.isfinite(frames).all():
        raise UploadUnreadableError("the upload holds samples that are not finite")
    return UploadedSound(pcm=frames, rate_hz=float(rate), digest=hashlib.sha256(data).hexdigest())
