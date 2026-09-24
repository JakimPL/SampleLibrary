from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from samplecore.config import ConfigurationError
from samplecore.config_editing import LibrarySources
from samplelibrary.app.folders import FolderListing, FolderUnreadableError, Place, list_folder, places
from samplelibrary.app.launcher import Launcher, SetupState
from samplelibrary.app.routes.guard import launcher_of, require_local_person

router = APIRouter(dependencies=[Depends(require_local_person)], tags=["setup"])

LauncherDependency = Annotated[Launcher, Depends(launcher_of)]


@router.get("/state")
def read_state(launcher: LauncherDependency) -> SetupState:
    return launcher.state()


@router.put("/sources")
async def choose_sources(sources: LibrarySources, launcher: LauncherDependency) -> SetupState:
    """Write the library's folders into the config file and open the library under them.

    Raises:
        HTTPException: 422 when the folders fail validation, naming what to change.
    """
    try:
        launcher.choose_sources(sources)
    except ConfigurationError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return launcher.state()


@router.get("/places")
def read_places() -> tuple[Place, ...]:
    return places()


@router.get("/folders")
def read_folder(path: Annotated[str, Query(min_length=1)]) -> FolderListing:
    """One folder's contents for the folder browser.

    Raises:
        HTTPException: 404 when the path names no folder the system lets this application list.
    """
    try:
        return list_folder(Path(path))
    except FolderUnreadableError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error


@router.post("/quit", status_code=status.HTTP_202_ACCEPTED)
def quit_application(request: Request) -> None:
    request_quit: Callable[[], None] = request.app.state.request_quit
    request_quit()
