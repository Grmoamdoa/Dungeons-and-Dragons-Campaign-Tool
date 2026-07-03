# Packaging and Release Builds

This project ships packaged desktop builds with `PyInstaller`.

Target outputs:
- macOS Apple Silicon: `.app` bundled into a `.dmg`
- Windows x64: frozen app bundled into an Inno Setup installer `.exe`

The packaged app intentionally does **not** bundle sample `.png` files or `.dcp` campaign files from the repository root. User-imported assets and saved campaign packages remain external user data.

## Prerequisites

### macOS
- macOS on Apple Silicon
- Python `3.13.x`
- `python3` available on `PATH`
- Xcode Command Line Tools available so `hdiutil` and standard system tools are present

### Windows
- Windows x64
- Python `3.13.x`
- `py` launcher or `python` available on `PATH`
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed

## Build Commands

Run these from the project root.

### macOS

```bash
./packaging/build_macos.sh 1.2.3
```

Output:
- `packaging/output/DND-Campaign-Presenter-1.2.3-macOS.dmg`

### Windows

```powershell
.\packaging\build_windows.ps1 -Version 1.2.3
```

Output:
- `packaging/output/DND-Campaign-Presenter-1.2.3-Windows-x64-Setup.exe`

Important:
- Upload the installer from `packaging\output`, not the app executable from `dist`.
- The executable in `dist\DND Campaign Presenter` depends on nearby files such as `_internal\python313.dll`; it will not run correctly if uploaded or downloaded by itself.

PowerShell note:
- Run `cd` and any later command as separate commands, or separate them with `;`.
- The packaging script creates and activates `.venv-packaging` for the build, so you do not need to manually run `.venv\Scripts\Activate.ps1` first.

Correct examples:

```powershell
cd "C:\path\to\Dungeons-and-Dragons-Campaign-Tool-main"
.\packaging\build_windows.ps1 -Version 1.2.3
```

```powershell
cd "C:\path\to\Dungeons-and-Dragons-Campaign-Tool-main"; .\packaging\build_windows.ps1 -Version 1.2.3
```

## What the Build Scripts Do

- create or reuse `.venv-packaging`
- install runtime dependencies from `requirements.txt`
- install build dependency from `packaging/requirements-build.txt`
- clean `build/`, `dist/`, and old packaging output
- run `PyInstaller` with `packaging/pyinstaller/dnd_campaign_presenter.spec`
- wrap the frozen app in a platform installer

## Smoke Test After Each Build

- Launch the installed app by double-clicking it.
- Confirm the main window opens without a terminal.
- Confirm audio failure is non-fatal by launching on a machine without a valid audio device if available.
- Import one image, one token, and one audio file.
- Save a `.dcp` project and reopen it.
- Open the main dialogs you expect users to use during a session.

## Distribution

Upload only the generated installer artifacts from `packaging/output` to GitHub Releases for the intended project repository.

Do not upload executables directly from `dist`. Those files are intermediate PyInstaller output and depend on the rest of their generated folder.

Do not use the current local `origin` remote as the release target unless it has been corrected to the real D&D Campaign Tool repository.
