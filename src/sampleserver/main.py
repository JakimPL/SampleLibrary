from __future__ import annotations

from samplecore.config import load_config
from sampleserver.app import create_app
from sampleserver.frontend import frontend_directory_from_environment

_config = load_config()

app = create_app(
    _config.catalog_url(),
    _config.library_root,
    _config.inference.url,
    frontend_directory=frontend_directory_from_environment(),
)
