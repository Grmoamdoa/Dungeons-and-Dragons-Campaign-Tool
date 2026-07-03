# Release Checklist

Use this checklist for each public packaged release.

## 1. Prepare the Release

- Confirm the GitHub repository is the correct project repository before publishing assets.
- Choose the release version, for example `1.2.3`.
- Review open issues that would block packaging or installation.
- Verify `README.md` installation steps still match the packaged release.

## 2. Build Clean Artifacts

- Build the macOS installer:
  - `./packaging/build_macos.sh <version>`
- Build the Windows installer:
  - `.\packaging\build_windows.ps1 -Version <version>`
- Confirm output file names:
  - `DND-Campaign-Presenter-<version>-macOS.dmg`
  - `DND-Campaign-Presenter-<version>-Windows-x64-Setup.exe`
- Confirm the Windows release upload comes from `packaging\output`, not from `dist`.
- Do not upload the standalone `.exe` inside `dist\DND Campaign Presenter`; it depends on nearby PyInstaller files such as `_internal\python313.dll`.

## 3. Smoke Test

- Launch the installed app without using a terminal.
- Confirm the main window opens without import errors.
- Confirm audio startup errors degrade gracefully and do not crash the app.
- Import image, audio, and token assets.
- Save and reload a `.dcp` project.
- Open and close the main dialogs used during a normal session.
- Confirm the packaged app does not require the source repository to remain on disk.

## 4. Generate Checksums

### macOS / Linux

```bash
shasum -a 256 packaging/output/DND-Campaign-Presenter-<version>-macOS.dmg
```

### Windows PowerShell

```powershell
Get-FileHash .\packaging\output\DND-Campaign-Presenter-<version>-Windows-x64-Setup.exe -Algorithm SHA256
```

Record the SHA256 values in the release notes.

## 5. Publish

- Create a GitHub Release in the intended project repository.
- Upload both installer artifacts from `packaging/output`.
- Add release notes that mention:
  - supported targets: macOS Apple Silicon and Windows x64
  - unsigned app warning expectations on macOS and Windows
  - SHA256 checksums
- Download each artifact from GitHub once and confirm the uploaded files match local checksums.

## 1.2.3 Release Status

- Done: source tree prepared for the `1.2.3` release.
- Done: repository ignores local build output, virtual environments, macOS metadata, and local `.dcp` campaign saves.
- Done: public-facing source files and release docs were scrubbed of personal names and machine-specific paths.
- Next: build the macOS and Windows installer artifacts with version `1.2.3`.
- Next: smoke test both installers, generate SHA256 checksums, and attach them to a GitHub Release tagged `v1.2.3`.
