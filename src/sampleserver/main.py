from __future__ import annotations

from samplecore.config import load_config
from samplecore.models.service_role import ServiceRole
from sampleserver.app import create_app
from sampleserver.frontend import frontend_directory_from_environment

_config = load_config()

app = create_app(
    _config.service_url(ServiceRole.READER),
    _config.library_root,
    _config.inference.url,
    role=ServiceRole.READER,
    frontend_directory=frontend_directory_from_environment(),
)
