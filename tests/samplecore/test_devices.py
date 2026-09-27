from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

import pytest
import torch

from samplecore.devices import CardCapability, runs_on, usable_cuda_card

CARD_NAME: Final[str] = "NVIDIA Test Card"
BUILT_ARCHITECTURES: Final[list[str]] = ["sm_75", "sm_86", "sm_120"]


@dataclass(frozen=True)
class ArchitectureCase:
    architecture: str
    capability: CardCapability
    runs: bool


@pytest.fixture(autouse=True)
def fresh_answer() -> Iterator[None]:
    usable_cuda_card.cache_clear()
    yield
    usable_cuda_card.cache_clear()


def _reachable_card(monkeypatch: pytest.MonkeyPatch, capability: CardCapability) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_device_capability", lambda: capability)
    monkeypatch.setattr(torch.cuda, "get_arch_list", lambda: BUILT_ARCHITECTURES)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda: CARD_NAME)


@pytest.mark.parametrize(
    "case",
    [
        ArchitectureCase("sm_86", (8, 6), runs=True),
        ArchitectureCase("sm_86", (8, 9), runs=True),
        ArchitectureCase("sm_90", (8, 9), runs=False),
        ArchitectureCase("sm_86", (9, 0), runs=False),
        ArchitectureCase("sm_120", (12, 0), runs=True),
        ArchitectureCase("compute_90", (12, 0), runs=True),
        ArchitectureCase("compute_90", (8, 6), runs=False),
        ArchitectureCase("gfx90a", (9, 0), runs=False),
    ],
    ids=lambda case: f"{case.architecture} on {case.capability[0]}.{case.capability[1]}",
)
def test_code_runs_on_its_own_major_version_upward_and_ptx_on_any_later_card(case: ArchitectureCase) -> None:
    assert runs_on(case.architecture, case.capability) is case.runs


def test_a_card_torch_carries_code_for_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    _reachable_card(monkeypatch, (8, 9))

    assert usable_cuda_card() == CARD_NAME


def test_a_card_older_than_torch_supports_leaves_work_on_the_processor(monkeypatch: pytest.MonkeyPatch) -> None:
    _reachable_card(monkeypatch, (6, 1))

    assert usable_cuda_card() is None


def test_a_machine_torch_reaches_no_card_on_computes_on_the_processor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    assert usable_cuda_card() is None
