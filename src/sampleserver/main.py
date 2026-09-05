from __future__ import annotations

from samplecore.config import load_config
from sampleserver.app import create_app

app = create_app(load_config().resolved_database_path)
