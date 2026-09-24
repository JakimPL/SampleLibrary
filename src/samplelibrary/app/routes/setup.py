from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from samplecore.config import ConfigurationError
from samplecore.config_editing import LibrarySources
from samplecore.models.base import FROZEN
from samplelibrary.app.folders import FolderListing, FolderUnreadableError, Place, list_folder, places
from samplelibrary.app.jobs import BuildTarget, JobAlreadyRunningError
from samplelibrary.app.launcher import Launcher, LibraryClosedError, SetupState
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


class BuildRequest(BaseModel):
    model_config = FROZEN

    target: BuildTarget


@router.post("/builds", status_code=status.HTTP_202_ACCEPTED)
def start_build(build_request: BuildRequest, launcher: LauncherDependency) -> SetupState:
    """Start building the library, and answer with the state the build shows in.

    Raises:
        HTTPException: 409 while the library is closed or another build runs.
    """
    try:
        launcher.build(build_request.target)
    except (LibraryClosedError, JobAlreadyRunningError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return launcher.state()


@router.post("/builds/cancel")
def cancel_build(launcher: LauncherDependency) -> SetupState:
    launcher.cancel_build()
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
