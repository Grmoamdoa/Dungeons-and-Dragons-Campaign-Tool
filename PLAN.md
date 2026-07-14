# Full Manual Controls

## Current work

- [x] Map the existing Full Manual behavior and hotkey system.
- [x] Add a configurable Full Manual master hotkey and menu action.
- [x] Add live, per-feature manual controls and persist them with encounter state.
- [x] Update rule checks, the Initiative Manager, and the user manual.
- [x] Compile and smoke-test the finished behavior.
- [x] Surface the Full Manual master and individual rule controls directly in the DM Control Panel.
- [x] Prepare the source and packaging defaults for version `1.2.4`.

## Next

Build and smoke-test the `1.2.4` macOS and Windows installer artifacts, then create the `v1.2.4` GitHub release. Future changes should retain the legacy migration that maps a saved `full_manual_mode: true` value to all individual controls.
