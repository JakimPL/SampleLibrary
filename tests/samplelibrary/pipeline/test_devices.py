from __future__ import annotations

from samplelibrary.pipeline.devices import AUTOMATIC_DEVICE, CPU_DEVICE, CUDA_DEVICE, available_device, resolved_device


def test_a_named_device_is_the_one_every_command_runs_on() -> None:
    assert resolved_device(CPU_DEVICE) == CPU_DEVICE
    assert resolved_device(CUDA_DEVICE) == CUDA_DEVICE


def test_the_automatic_device_is_whichever_this_machine_offers() -> None:
    assert resolved_device(AUTOMATIC_DEVICE) == available_device()
    assert available_device() in (CPU_DEVICE, CUDA_DEVICE)
