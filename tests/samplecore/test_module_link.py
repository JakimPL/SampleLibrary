from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from samplecore.models.module_link import MAXIMUM_URL_LENGTH, ModuleLink


@dataclass(frozen=True)
class UrlCase:
    url: str
    accepted: bool


URL_CASES = (
    UrlCase("https://www.modules.pl/?id=module&mod=9752", accepted=True),
    UrlCase("http://example.org/x", accepted=True),
    UrlCase("https://example.org/" + "x" * (MAXIMUM_URL_LENGTH - len("https://example.org/")), accepted=True),
    UrlCase("https://example.org/" + "x" * MAXIMUM_URL_LENGTH, accepted=False),
    UrlCase("ftp://example.org/x", accepted=False),
    UrlCase("modules.pl/x", accepted=False),
    UrlCase("https:///x", accepted=False),
    UrlCase("https://a b/x", accepted=False),
    UrlCase("", accepted=False),
)


@pytest.mark.parametrize("case", URL_CASES, ids=lambda case: case.url[:40] or "empty")
def test_a_link_takes_an_absolute_web_address_naming_a_host(module_hash_a: str, case: UrlCase) -> None:
    if case.accepted:
        assert ModuleLink(module_hash=module_hash_a, url=case.url).url == case.url
    else:
        with pytest.raises(ValidationError):
            ModuleLink(module_hash=module_hash_a, url=case.url)
