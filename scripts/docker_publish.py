from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Final

from paths import POSTGRES_ENVIRONMENT_FILE, SITE_ENVIRONMENT_FILE
from sqlalchemy.engine import URL, make_url

from samplecore.config import PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE, PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE

POSTGRES_PASSWORD_VARIABLE: Final[str] = "POSTGRES_PASSWORD"
POSTGRES_PORT_VARIABLE: Final[str] = "POSTGRES_PORT"
READER_URL_VARIABLE: Final[str] = "SAMPLERIPPER_SERVER_DATABASE_URL"
DEFAULT_POSTGRES_PORT: Final[int] = 5432
LOOPBACK: Final[str] = "127.0.0.1"
OWNER: Final[str] = "sampleripper"
DATABASE: Final[str] = "sampleripper"


def main(argv: list[str]) -> None:
    """Publish a library into the Postgres `docker-compose.yml` runs, as its site then reads it.

    The server's password and the reader's come from the files `just docker-secrets` wrote, handed
    to `sampleripper publish` in its environment alone. Everything on the command line goes before
    `publish`, such as ``--config dev-library/config.toml`` to publish the sandbox.
    """
    postgres = _read_environment_file(POSTGRES_ENVIRONMENT_FILE)
    reader = make_url(_read_environment_file(SITE_ENVIRONMENT_FILE)[READER_URL_VARIABLE])
    target = URL.create(
        "postgresql+psycopg",
        username=OWNER,
        password=postgres[POSTGRES_PASSWORD_VARIABLE],
        host=LOOPBACK,
        port=int(os.environ.get(POSTGRES_PORT_VARIABLE, DEFAULT_POSTGRES_PORT)),
        database=DATABASE,
    )
    environment = {
        **os.environ,
        PUBLISH_DATABASE_URL_ENVIRONMENT_VARIABLE: target.render_as_string(hide_password=False),
        PUBLISH_READER_PASSWORD_ENVIRONMENT_VARIABLE: reader.password or "",
    }
    completed = subprocess.run([sys.executable, "-m", "sampleripper", *argv, "publish"], env=environment, check=False)
    sys.exit(completed.returncode)


def _read_environment_file(path: Path) -> dict[str, str]:
    """The settings a compose environment file holds, one ``NAME=value`` per line.

    Raises:
        SystemExit: the file is missing, which `just docker-secrets` writes.
    """
    if not path.is_file():
        sys.exit(f"{path} is missing; `just docker-secrets` writes it.")
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


if __name__ == "__main__":
    main(sys.argv[1:])
