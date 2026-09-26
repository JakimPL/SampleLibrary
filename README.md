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
takes several minutes. On Windows and Linux with an NVIDIA graphics card, it takes the packages that
let the card do the heavy listening instead, several gigabytes more. Later starts take a few
seconds. SampleLibrary then opens in your browser on its setup page:

1. Under **Your folders**, choose your module folder, your sample folders, or both.
2. Choose where the library keeps its files. Pick a drive with free space: a large collection takes
   several gigabytes.
3. Click **Save and open the library**.
4. Under **Your library**, click **Build my library**. The build lists its steps with the time
   each took, and a long step shows the time it has left. Once it finishes, click **Open the
   library** at the top.

**Build the cloud**, on until you switch it off, has the build listen to every sample and lay out
the cloud. The first time, it downloads a listening model of about 1 GB. An NVIDIA graphics card
makes this much faster, and the setup page names the card it uses. Without one, a large collection
takes a day or more, so the page asks before it starts.

## Everyday use

- Open SampleLibrary from the Start menu, from Applications, or from its AppImage. A start while it
  already runs opens it in your browser again. A new version closes the old one as it starts.
- A build keeps going when you close the browser tab.
- To add folders, or to build again after your collection grows, open **Library → Setup**.
- **Library → Quit SampleLibrary**, or **Quit** on the setup page, stops SampleLibrary.

[Using SampleLibrary](docs/using.md) explains the cloud, the morph, every click and key, and using
the app on a phone or tablet. The app shows the same list under **Help → Keyboard and mouse**.

## When something goes wrong

If the first start stops before SampleLibrary opens, a download was interrupted. Start SampleLibrary
again: it reuses every file it finished downloading.

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
