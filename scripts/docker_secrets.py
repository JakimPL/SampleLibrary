from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

from paths import POSTGRES_ENVIRONMENT_FILE, SITE_ENVIRONMENT_FILE

from samplecore.passwords import new_password
from samplecore.storage.atomic import PRIVATE_FILE_MODE, write_bytes_atomically

POSTGRES_PASSWORD_VARIABLE: Final[str] = "POSTGRES_PASSWORD"
READER_URL_VARIABLE: Final[str] = "SAMPLERIPPER_SERVER_DATABASE_URL"
READER_URL_TEMPLATE: Final[str] = "postgresql+psycopg://sampleripper_reader:{password}@postgres:5432/sampleripper"


def main() -> None:
    """Write the passwords `docker-compose.yml` reads, each chosen here and readable by its owner alone.

    The database server's own superuser password and the reader's connection go to two files, so
    the site's container is handed the reader's credentials and never the superuser's. A file
    already there is kept, since the server it opened was initialized with its password.
    """
    written = [
        path
        for path, content in (
            (POSTGRES_ENVIRONMENT_FILE, f"{POSTGRES_PASSWORD_VARIABLE}={new_password()}\n"),
            (SITE_ENVIRONMENT_FILE, f"{READER_URL_VARIABLE}={READER_URL_TEMPLATE.format(password=new_password())}\n"),
        )
        if _write_new(path, content)
    ]
    for path in written:
        print(f"Wrote {path}.")
    if not written:
        print("Both files are already there, and stay as they are.", file=sys.stderr)


def _write_new(path: Path, content: str) -> bool:
    if path.exists():
        return False
    write_bytes_atomically(path, content.encode("utf-8"), mode=PRIVATE_FILE_MODE)
    return True


if __name__ == "__main__":
    main()
