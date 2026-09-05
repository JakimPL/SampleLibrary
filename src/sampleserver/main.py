from __future__ import annotations

from samplecore.config import load_config
from sampleserver.app import create_app

_config = load_config()

app = create_app(_config.resolved_database_path, _config.library_root)
