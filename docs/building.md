# Building and releasing

This guide is for building the SampleLibrary executable and its installers, and for publishing a
release. Running the app from a checkout takes [Running from source](source.md) alone.

## What gets built

```
build/
  frontend/               the built web app
  package/                the samplelibrary wheel, which carries the web app, and its pinned requirements
bin/SampleLibrary         the executable (SampleLibrary.exe on Windows)
dist/                     what a release publishes
  SampleLibrary-<version>-windows-x64-setup.exe
  SampleLibrary-<version>-macos-arm64.dmg
  SampleLibrary-<version>-linux-x64.AppImage
  descriptor/             the pretrained descriptor, when you publish a new one
```

Each system builds its own executable and installer: build on Windows for Windows, on a Mac with
Apple silicon for macOS, and on Linux for Linux. The Application workflow builds all three on GitHub
(see [Continuous integration](#continuous-integration)).

## Prerequisites

Everything [Running from source](source.md#requirements) lists, and for each step:

| Step | Needs |
|---|---|
| `just package` | Node.js and npm, and uv |
| `just executable` | Rust, installed with [rustup](https://rustup.rs): cargo compiles the launcher |
| `just installer` on Windows | [Inno Setup 6](https://jrsoftware.org/isinfo.php) |
| `just installer` on macOS | `codesign` and `hdiutil`, which come with macOS |
| `just installer` on Linux | appimagetool, which the build downloads itself |

## Building

```sh
just package      # build/: the web app, the wheel carrying it, and its pinned requirements
just executable   # bin/: the executable for this system
just installer    # dist/: the installer for this system
```

- `just package` builds the web app and the samplelibrary wheel. It also writes the exact versions
  the app installs, taken from `uv.lock`, with torch's processor build, which spares every
  installation gigabytes of NVIDIA libraries. trackmod is pinned to the submodule's version, which
  installations take from PyPI.
- `just executable` compiles a [PyApp](https://ofek.dev/pyapp/) launcher around a copy of the wheel
  that carries those versions. On its first start, the executable downloads Python and installs the
  app with uv, which takes several minutes; later starts take seconds.
- `just installer` wraps the executable for its system:
  - The Windows installer puts it in the person's own programs folder, with a Start menu shortcut
    and an optional desktop one. Upgrading and uninstalling first quit the running app and remove the packages the
    earlier version installed; the library stays.
  - The macOS disk image holds an app bundle whose launcher sends the app's output to the log
    folder and announces the first start. The bundle carries an ad hoc signature.
  - The Linux AppImage's launcher does the same with a desktop notification.

## Trying a build

Run `bin/SampleLibrary`: it installs itself, starts, and opens your browser, as an installed copy
does. An executable installs its packages once per version, and a new build of the same version
starts on the packages the first one installed. `bin/SampleLibrary self remove` deletes that
installation, so the next start installs afresh. The installations live in PyApp's data folder:
`~/.local/share/pyapp` on Linux, `~/Library/Application Support/pyapp` on macOS and
`%LOCALAPPDATA%\pyapp\data` on Windows.

## Continuous integration

The Application workflow (`.github/workflows/app.yml`) builds everything on GitHub:

1. It checks the inputs of the build (see [Releasing](#releasing)) and runs `just package` once.
2. On Linux, Windows and macOS, it runs `just executable`, then installs the executable on the fresh
   machine and walks it through a first session (`scripts/smoke_test_app.py`). The session writes 30
   generated modules, opens a library on the built-in database, builds its catalog, quits, and
   checks that the database stopped. Then it runs `just installer`.
3. Each run keeps the executables and installers it built, to download from the run's page. A run
   whose smoke test fails keeps the library's logs as well.

Start a run from the repository's Actions tab: **Application**, then **Run workflow**. That button
appears once the workflow is on the default branch.

## Releasing

1. **Set the version** in `pyproject.toml`. Every release takes a new version, since an executable
   reuses the packages it installed for a version it has seen.
2. **Check trackmod.** Installations take the submodule's trackmod version from PyPI; TrackMod
   publishes a version when its own `v<version>` tag is pushed. The workflow stops while PyPI lacks
   it.
3. **Publish the pretrained descriptor**, when it changed. After training it on your library, run
   `just release-descriptor <tag>`, such as `just release-descriptor descriptor-1`. It writes the file
   to upload into `dist/descriptor/`, and the record new libraries download it by into
   `src/sampledescriptor/pretrained.toml`. Create a GitHub release with that tag, upload the file to
   it, and commit the record. The workflow downloads the file and checks it against the record.
4. **Tag the release** and push the tag, such as `git tag v0.1.0` and `git push origin v0.1.0`. The
   tag must name the version from step 1.
5. **Publish the draft.** The workflow drafts a GitHub release carrying the three installers.
   Review it, add notes, and publish it.

## Signing

The installers are unsigned, so Windows shows its SmartScreen warning and macOS asks the person to
confirm the app once; the [README](../README.md#install) walks them through both. Signing takes a
code-signing certificate for Windows, and an Apple Developer ID for macOS, where Apple also
notarizes the app.
