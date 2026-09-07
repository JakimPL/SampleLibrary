from __future__ import annotations

from samplecore.config import load_config
from sampleserver.app import create_app

_config = load_config()

app = create_app(_config.database_url, _config.library_root)
