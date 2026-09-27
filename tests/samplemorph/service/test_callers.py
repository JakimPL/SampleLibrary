from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from samplemorph.service.callers import ProgramsCallingItsAddressOnly

LISTENING_HOST: Final[str] = "192.168.1.10"


@dataclass(frozen=True)
class CallerCase:
    base_url: str
    headers: dict[str, str]
    answered: bool


CALLER_CASES: Final[tuple[CallerCase, ...]] = (
    CallerCase("http://127.0.0.1:8010", {}, answered=True),
    CallerCase("http://localhost:8010", {}, answered=True),
    CallerCase(f"http://{LISTENING_HOST}:8010", {}, answered=True),
    CallerCase("http://127.0.0.1:8010", {"origin": "https://elsewhere.example"}, answered=False),
    CallerCase("http://127.0.0.1:8010", {"origin": "http://127.0.0.1:8010"}, answered=False),
    CallerCase("http://rebound.example:8010", {}, answered=False),
)


def _guarded() -> FastAPI:
    application = FastAPI()

    @application.post("/morph/response")
    def respond() -> dict[str, bool]:
        return {"rendered": True}

    application.add_middleware(ProgramsCallingItsAddressOnly, host=LISTENING_HOST)
    return application


@pytest.mark.parametrize("case", CALLER_CASES, ids=lambda case: f"{case.base_url} {case.headers}")
def test_the_renderer_answers_programs_calling_its_address_and_no_web_page(case: CallerCase) -> None:
    """A page sends an Origin with every request it makes elsewhere, a plain post among them; a program sends none."""
    with TestClient(_guarded(), base_url=case.base_url) as client:
        response = client.post("/morph/response", headers=case.headers)

    assert (response.status_code == 200) is case.answered
