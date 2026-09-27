from __future__ import annotations

from typing import Final

PYPI_INDEX: Final[str] = "https://pypi.org/simple"
CPU_TORCH_INDEX: Final[str] = "https://download.pytorch.org/whl/cpu"
CUDA_TORCH_INDEX: Final[str] = "https://download.pytorch.org/whl/cu128"
# The NVIDIA launcher's wheel carries this local version label, which gives its installation a
# folder of its own: PyApp names the folder by the project's name and version alone.
CUDA_LOCAL_VERSION: Final[str] = "cu128"
# The lowest CUDA version a driver reports for the NVIDIA launcher, which runs on any driver of the
# CUDA major version its torch build was made with.
MINIMUM_DRIVER_CUDA_MAJOR: Final[int] = 12
