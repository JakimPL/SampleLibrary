from __future__ import annotations

from typing import Annotated, Final
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.scalars import ModuleHash

MAXIMUM_URL_LENGTH: Final[int] = 2048
PAGE_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})


def page_url(url: str) -> str:
    """``url`` as a browser opens a page by it: an absolute http or https address naming a host.

    Raises:
        ValueError: the address is longer than ``MAXIMUM_URL_LENGTH``, holds whitespace, uses
            another scheme, or names no host.
    """
    if len(url) > MAXIMUM_URL_LENGTH:
        raise ValueError(f"a page address is at most {MAXIMUM_URL_LENGTH} characters long")
    if any(character.isspace() for character in url):
        raise ValueError(f"{url!r} holds whitespace")
    parts = urlsplit(url)
    if parts.scheme not in PAGE_SCHEMES:
        raise ValueError(f"{url!r} must start with http:// or https://")
    if not parts.hostname:
        raise ValueError(f"{url!r} names no host")
    return url


PageUrl = Annotated[str, AfterValidator(page_url)]


class ModuleLink(BaseModel):
    """The web page a cataloged module came from, keyed by the module's content hash.

    The hash follows the file's bytes, so the link holds for every copy of the module, whichever
    name and folder each was read from.
    """

    model_config = FROZEN

    module_hash: ModuleHash
    url: PageUrl
