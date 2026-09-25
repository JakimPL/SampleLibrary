# SampleLibrary

SampleLibrary gathers every sample from your tracker modules (XM, IT, MOD, S3M) and your folders of
audio files into one library you browse in your web browser. It keeps one copy of each sample,
groups near-duplicates, and lets you play, label and rate every sample. The cloud lays out the
whole library by how the samples sound, and the morph plays the sounds between any two of them.

## Install

Download the file for your system from the
[Releases](https://github.com/JakimPL/SampleLibrary/releases) page:

- **Windows** (64-bit): run `SampleLibrary-<version>-windows-x64-setup.exe`. It installs
  SampleLibrary for you alone and adds it to the Start menu. If Windows warns about an unrecognized
  app, click **More info**, then **Run anyway**.
- **macOS** (Apple silicon): open `SampleLibrary-<version>-macos-arm64.dmg` and drag SampleLibrary
  into Applications. The first time you open it, macOS asks you to confirm an app from outside the
  App Store: go to **System Settings → Privacy & Security** and click **Open Anyway**.
- **Linux** (64-bit): allow `SampleLibrary-<version>-linux-x64.AppImage` to run as a program, in its
  file properties or with `chmod +x`, then open it.

## First start

The first start downloads Python and the packages SampleLibrary runs on, about 2 GB on disk, which
takes several minutes. Later starts take a few seconds. SampleLibrary then opens in your browser on
its setup page:

1. Choose your module folder, your sample folders, or both.
2. Choose where the library keeps its files. Pick a drive with free space: a large collection takes
   several gigabytes.
3. Click **Save and open the library**, then **Scan my folders**.

**Scan and build the cloud** also listens to every sample and lays out the cloud. The first time,
it downloads a listening model of about 1 GB, and on a large collection it takes hours.

## Everyday use

- Open SampleLibrary from the Start menu, from Applications, or from its AppImage. A start while it
  already runs opens it in your browser again.
- A scan keeps going when you close the browser tab.
- To add folders, or to scan again after your collection grows, open **View → Library setup**.
- **Quit** on the setup page stops SampleLibrary.

[Using SampleLibrary](docs/using.md) explains the cloud, the morph, every click and key, and using
the app on a phone or tablet. The app shows the same list under **View → Keyboard and mouse**.

## When something goes wrong

SampleLibrary keeps a log you can read or attach to a report:

| System | Log folder |
|---|---|
| Windows | `%LOCALAPPDATA%\SampleLibrary\Logs` |
| macOS | `~/Library/Logs/SampleLibrary` |
| Linux | `~/.local/state/SampleLibrary/log` |

Report a problem on the [issue tracker](https://github.com/JakimPL/SampleLibrary/issues), with the
log attached.

Uninstalling SampleLibrary on Windows removes the program and the packages it downloaded. Your
library stays in the folder you chose for it.

## Documentation

- [Using SampleLibrary](docs/using.md): the cloud, the morph, keys and gestures, phones and tablets.
- [Running from source](docs/source.md): running SampleLibrary from a checkout, with its commands
  and every setting.
- [Development](docs/development.md): checks, tests and the sandbox library, for contributors.
- [Building and releasing](docs/building.md): building the executable and the installers, and
  publishing a release.
- [Architecture](docs/architecture.md): how the code is organized, and why.
