from __future__ import annotations

from typing import Final

import httpx

INFERENCE_TIMEOUT_SECONDS: Final[float] = 30.0
STATUS_TIMEOUT_SECONDS: Final[float] = 2.0


def build_inference_client(url: str) -> httpx.AsyncClient:
    """One client for the morph inference process, kept open for the app's lifetime so its connections are reused."""
    return httpx.AsyncClient(base_url=url, timeout=INFERENCE_TIMEOUT_SECONDS)


def unavailable_detail(url: str) -> str:
    """What a caller is told when no inference process answers, naming where one was expected."""
    return f"morph rendering is unavailable: no inference process answers at {url}"


def timed_out_detail(url: str) -> str:
    """What a caller is told when the inference process takes longer than a render is waited for."""
    return f"the inference process at {url} did not finish the render within {INFERENCE_TIMEOUT_SECONDS:g} seconds"
