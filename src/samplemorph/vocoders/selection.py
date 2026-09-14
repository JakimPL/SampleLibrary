from __future__ import annotations

from pathlib import Path

from samplemorph.model_paths import restorer_path
from samplemorph.registries import RESTORED_VOCODER_NAME, VOCODER_REGISTRY
from samplemorph.vocoders import Vocoder


def vocoder_named(name: str, *, library_root: Path, restorer_name: str, device: str) -> Vocoder:
    """Build the vocoder a name picks, loading its fitted model when the vocoder reads one.

    The restored path reads its restorer from the library root, so it takes the name to read and
    the device to run on; every other vocoder is built from its name alone. The restorer's own
    module is imported only on that path, which keeps a process that renders through phase
    integration alone clear of torch.

    Raises:
        FileNotFoundError: the restored vocoder was asked for and no restorer is stored under that name.
    """
    if name == RESTORED_VOCODER_NAME:
        # pylint: disable-next=import-outside-toplevel
        import torch

        # pylint: disable-next=import-outside-toplevel
        from samplemorph.vocoders.restored import load_restorer

        return load_restorer(restorer_path(library_root, name=restorer_name), device=torch.device(device))

    return VOCODER_REGISTRY[name]()
