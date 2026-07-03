# D&D Campaign Tool

Desktop app for running tabletop sessions with:
- Timeline-based image/audio presentation
- Battle-map encounter flow

Current MVP status:
- Portable `.dcp` save/load package format
- Presentation mode with operator controls + player-facing output
- Encounter runtime state persistence
- Computer-wide configurable hotkeys for top-level menu commands
- Encounter setup supports multi-stage maps with per-stage tokens, fog/cloud squares, and visible difficult terrain squares
- DM control panel supports multi-select token moves and reserve/active updates
- DM control panel token list expands up to 10 visible encounter tokens before scrolling

## Install Packaged App

Packaged installers are the recommended way to use the 1.2 release.

Download the latest installer from GitHub Releases in the intended project repository:
- macOS Apple Silicon: `DND-Campaign-Presenter-1.2.3-macOS.dmg`
- Windows x64: `DND-Campaign-Presenter-1.2.3-Windows-x64-Setup.exe`

Unsigned release note:
- macOS may warn that the app is from an unidentified developer.
- Windows SmartScreen may warn before launch.
- This is expected until code signing/notarization is added.

### macOS

1. Open the downloaded `.dmg`.
2. Drag `D&D Campaign Presenter.app` into `Applications`.
3. Open the app from `Applications`.
4. If Gatekeeper blocks the first launch, open the app from Finder and allow it in the system prompt.

### Windows

1. Run `DND-Campaign-Presenter-1.2.3-Windows-x64-Setup.exe`.
2. Complete the installer steps.
3. Launch the app from the Start Menu or desktop shortcut.
4. If SmartScreen warns on first launch, choose the option to continue if you trust the download source.

## Run From Source

The steps below are only for running the app from source during development or if you are not using the packaged installers.

## Quick Overview (For First-Time Terminal Users)

If you have never used a terminal before, this is the full process:

1. Install Python.
2. Open a terminal.
3. Move into this project folder.
4. Create a virtual environment (`.venv`).
5. Install required packages.
6. Start the app.

Copy and run one command at a time. Press `Enter` after each line.

## 0. Make Sure You Have the Project Folder

Before running commands, confirm this folder exists on your computer:

`Dungeons-and-Dragons-Campaign-Tool-main`

If you downloaded a ZIP, extract it first so you can open that folder in terminal.

## 1. Install Python (One Time)

1. Install Python `3.13.x` (recommended) or `3.14.x` from [python.org/downloads](https://www.python.org/downloads/).
2. On Windows, make sure you check `Add python.exe to PATH` during install.

## 2. Open a Terminal

- macOS: Open `Terminal` (Applications > Utilities, or search with Spotlight).
- Windows: Open `PowerShell` (recommended) from Start menu.
- Linux: Open your normal terminal app.

## 3. Verify Python Is Installed

Try this first:

```bash
python --version
```

If that fails, try one of these:

```bash
python3 --version
```

```powershell
py --version
```

Expected result: a version like `Python 3.13.x` or `Python 3.14.x`.

## 4. Go to the Project Folder

In the terminal, use `cd` to enter the folder that contains this `README.md`.

macOS example:

```bash
cd "/path/to/Dungeons-and-Dragons-Campaign-Tool-main"
```

Windows example:

```powershell
cd "C:\path\to\Dungeons-and-Dragons-Campaign-Tool-main"
```

Optional check (shows files in this folder):

```bash
ls
```

On Windows Command Prompt (CMD), use:

```bat
dir
```

You should see files like `main.py` and `requirements.txt`.

## 5. First-Time Setup + Run

Run only the section for your system.

Dependency note:
- Python `3.13.x` installs `pygame`.
- Python `3.14.x` installs `pygame-ce` automatically from `requirements.txt` (same `import pygame` API used by this app).

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

If PowerShell blocks activation, run this once in the same PowerShell window, then run activation again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Windows Command Prompt (CMD)

```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## 6. Next Time You Open the App

After the first setup, you do **not** need to reinstall packages every time.

### macOS / Linux

```bash
cd "/path/to/Dungeons-and-Dragons-Campaign-Tool-main"
source .venv/bin/activate
python main.py
```

### Windows PowerShell

```powershell
cd "C:\path\to\Dungeons-and-Dragons-Campaign-Tool-main"
.venv\Scripts\Activate.ps1
python main.py
```

### Windows CMD

```bat
cd C:\path\to\Dungeons-and-Dragons-Campaign-Tool-main
.venv\Scripts\activate.bat
python main.py
```

## 7. How to Close the App

1. Close the app window.
2. Optional: return terminal to normal with:

```bash
deactivate
```

## Save Format

- Default save format is portable `.dcp`.
- Use Save/Load in the app to package campaign data and referenced assets.

## Audio Notes

- If `pygame` mixer initialization fails, the app still opens.
- In that case, audio playback is unavailable and a warning is shown.
- If audio is missing, check your OS output device and relaunch.

## Troubleshooting

### `ModuleNotFoundError` or missing package errors

Usually means:
- Virtual environment is not active, or
- Dependencies were not installed in the active environment.

Fix:

macOS/Linux:

```bash
cd "/path/to/Dungeons-and-Dragons-Campaign-Tool-main"
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
cd "C:\path\to\Dungeons-and-Dragons-Campaign-Tool-main"
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### `python: command not found` (or similar)

Try:

```bash
python3 --version
```

or on Windows:

```powershell
py --version
```

### PyQt plugin/load errors

Reinstall dependencies in the active virtual environment:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Windows: `Failed to build 'pygame'` / `distutils.msvccompiler` error

This usually happens when `pip` tries to build legacy `pygame` from source on newer Python versions.

Fix options:

1. Use the latest project copy (this repo now installs `pygame-ce` automatically on Python `3.14+`) and rerun:

```powershell
pip install -r requirements.txt
```

2. If you are using an older project copy, use Python `3.13` for this project:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Pygame mixer/device errors

- Close other apps that might be using audio.
- Switch your OS output device, then relaunch.
- You can still use non-audio features if mixer initialization keeps failing.

## Quick Sanity Check

1. Launch app with `python main.py`.
2. Import one image and one audio file.
3. Place both on the timeline and press Play.
4. Save project as `.dcp`.
5. Reload that `.dcp` and confirm clips still work.
6. If the first timeline scene is an encounter, press Play after reload and confirm its tokens appear without reopening Encounter Setup.
7. For a multi-stage encounter, confirm stage maps, tokens, fog/cloud squares, and difficult terrain squares survive save/load and player-view rendering.
8. In a presentation session, select movement for a token hidden by Hide Token fog and confirm the player view does not show the token cursor/path or green movement range; hide a separate token from players and confirm visible-token green range and yellow path previews do not reveal its occupied squares.
9. Paint difficult terrain in setup and live battle, confirm players can see the terrain texture, tokens render above it, and entering terrain costs an extra 5 ft of movement.
10. In the DM Live Control Panel, confirm Grid Settings shows fog controls beside the difficult-terrain toggle, and that grid coordinate labels remain readable after zooming into the DM map.
11. In the DM Live Control Panel, multi-select encounter tokens and confirm `Set Hidden` / `Set Visible` updates player-view visibility for all selected tokens, including mixed visible/hidden selections.
12. In battle, add `Invisible` to a token and confirm the DM map shows a translucent `HID` token with coordinates while the player view hides the token and its movement preview; then remove `Invisible` and confirm it returns.

## Known-Good Baseline

- Python `3.13.2`
- Python `3.14.x`
- PyQt6 `6.9.0`
- pygame `2.6.1` (Python `3.13.x`)
- pygame-ce `2.5+` (Python `3.14.x`)

## Packaging Maintainer Notes

Packaged release tooling lives under `packaging/BUILDING.md` and `packaging/RELEASE_CHECKLIST.md`.

Current packaging strategy:
- `PyInstaller` freezes the app from `main.py`.
- macOS builds produce a `.app` and wrap it in a `.dmg`.
- Windows builds produce an Inno Setup installer `.exe`.
