"""User manual content for the in-app Help dialog."""

USER_MANUAL_MARKDOWN = """
# D&D Campaign Presenter User Manual

## 1) What This App Does
This tool combines two linked modes:
- Timeline presentation for scene and audio playback.
- Encounter mode for tactical combat on a battle map.

You build clips in the timeline, trigger encounters from battle markers, then return to presentation flow.

## 2) Quick Start Workflow
1. Import assets.
2. Drag image and audio assets onto timeline tracks.
3. Insert encounter clips where combat should trigger.
4. Configure encounter clips (map, grid, tokens, optional battle music).
5. Run with Play, Stop, Next Scene, and Delete Selected Clip.
6. Save regularly as `.dcp` for portability.
7. If you hit issues during use, open `Help -> Feedback Notes...` and capture a report.

## 3) Asset Import Rules (Important Quirks)
- Supported asset formats:
  - Images: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.gif`
  - Audio: `.mp3`, `.ogg`, `.wav`, `.flac`
  - Token auto-detect applies to `.png`, `.gif`, and `.webp`
- Token auto-classification is naming based: supported token images are recognized when the filename stem includes a token marker such as `(token)`. Spaces / underscores / hyphens are normalized away, so forgiving variants like `goblin_(token).png`, `goblin-token).webp`, or `goblin (token).gif` are usually detected.
- If you select the Tokens import filter, supported token extensions can still classify as tokens even without a token marker in the filename.
- Without a token marker/filter hint, image extensions default to Images and audio extensions default to Audio.
- Duplicate asset paths in a category are skipped.

## 4) Asset Bin Usage
- Use tabs to review Images, Audio, and Tokens.
- Drag Images and Audio from Asset Bin to timeline tracks.
- Drag Tokens to Encounter Setup map preview or the active battle map.
- Token placement blocks occupied grid cells / token footprints in setup preview and battle-map drop handling.
- Right-click selected assets (or press `Delete` while focused in an asset list) to remove them from the current project asset bin. Existing timeline/encounter references are not rewritten automatically.

## 5) Timeline Editing and Playback
- Click timeline/ruler to set playhead time.
- Single-click any clip (Image, Audio, or Battle) to select it.
- Drag image/audio clips to move; drag right edge to resize duration.
- Battle clips are fixed-width markers (not normal duration clips).
- Start/Duration text fields accept `M:SS.hh` style parsing.
- `Next Scene` jumps to the next clip start when playback is paused.
- `Delete Selected Clip` removes the currently selected clip (button appears after `Next Scene`; Backspace shortcut also works while editing).
- Playback auto-stops and resets when timeline end is reached.

## 6) Encounter Clips and Setup Dialog
- Use `Insert Encounter` to add a battle marker.
- Double-click a battle clip to open Encounter Setup.
- Encounter Setup includes:
  - Map selection
  - Grid show/size/offset
  - Optional battle music from imported audio, including encounter music volume and whether it replays when finished
  - Token placement by drag/drop
- Preview map controls:
  - Mouse wheel or the `+` / `-` buttons zoom the setup preview.
  - `Fit` resets preview zoom to the full-map fit.
  - Middle-click drag pans the preview while zoomed in.
- Token footprints use profile size (for example, Large creatures can occupy `2x2` squares).
- Tokens can also use rectangular footprints (for example `2x1`), not just square sizes.
- Click a placed token in preview to remove it (clicking any occupied square of a larger token removes it).
- Right-click a token entry in setup list to edit its profile.
- Initiative is set during encounters from DM tools, not from token profiles.

## 7) Presentation Session (Operator + Player Separation)
- Start from `View -> Start Presentation Session`.
- Player View opens fullscreen as output-only display.
- Screen preference: secondary monitor if present, otherwise primary.
- Timeline/asset editing controls are intentionally disabled during presentation mode; token profile tools remain available for live encounter management.
- Transport controls remain active.
- During encounters, player output mirrors battle snapshots.
- Player battle view includes the active-turn arrow and movement range/path indicators during movement selection.
- After encounter end, player output returns to presentation content.

## 8) Hotkey Settings
- Open `Edit -> Hotkey Settings...` to assign optional hotkeys for top-level menu commands.
- `Edit -> Insert Encounter...` can be assigned a custom hotkey for creating encounter clips.
- New hotkeys start blank; existing standard shortcuts such as Save/Open/Quit and Backspace delete remain available.
- Hotkeys are saved computer-wide for the current OS user and apply to every campaign opened on that computer.
- Duplicate hotkeys and shortcuts reserved by built-in app actions are blocked.
- Configured hotkeys work while the app is focused, including during active encounters and while DM tool windows are open.

## 9) DM Live Control Panel (Presentation-Time Runtime Controls)
- Open from `View -> Open DM Control Panel` or `DM Panel` in presentation controls.
- This panel applies non-destructive runtime overrides unless you explicitly apply/overwrite them.
- Session Controls:
  - `Play/Pause` controls timeline playback while in presentation view.
  - `End Encounter` is enabled only while an encounter is active.
- Encounter Token Controls:
  - During active encounters, this section lists encounter tokens with HP, initiative, and status.
  - `Manage Initiative...` opens Initiative Manager for quick initiative entry and turn-order updates. It is also available from `View -> Manage Initiative...`.
  - In Initiative Manager, use `Set Teams...` to create `0-8` team buckets and drag tokens between buckets.
  - Team assignments affect combat hostility checks (same-team tokens do not trigger opportunity attacks against each other).
  - `Full Manual` disables initiative requirements plus turn / movement / action enforcement and combat automations until you turn it back off.
  - `Apply` validates initiative values and applies initiative/team changes together.
  - `Refresh` reloads the current encounter state into the Initiative Manager.
  - Initiative Manager can also `Generate New Token...` during an active encounter, choose how many to create, place each token on the map, then use `Set Generated Token Values` for each token (in placement order) to name them, set combat values (including token size / footprint), choose token art from the asset bin, and set visual fit / status values.
  - `Edit Profile...` opens the `Token Profile Management` dialog first, so you can pick which token profile to edit.
  - From Token Profile Management, click `Edit Profile...` to open the profile editor.
  - Profile edits now sync to matching placed tokens on the battle map immediately after saving (including footprint size / visual-fit changes).
- Mini timeline features:
  - Hover shows a thin vertical guide and exact cursor time readout.
  - Clip blocks display clip names (elided if narrow).
  - `Move Clips` mode lets you drag clips to adjust runtime start positions.
  - `Draw Skip Range` mode lets you click-drag to draft a skip interval.
- Skip ranges:
  - Drawn ranges populate start/end inputs; click `Add Range` to commit.
  - `Add From Playhead (+5s)` creates a 5-second skip range starting at the current playhead.
  - `Remove Selected Range` deletes the selected session skip range.
  - Inputs prefer numeric seconds and also accept `M:SS.hh` format.
  - Ranges are session-only and do not persist to authored timeline by default.
- Clip controls:
  - Hide/unhide clip (non-destructive runtime skip).
  - Move and place controls for quick sequence adjustments.
  - Start/duration edits for image/audio clips.
  - Volume override for audio clips and battle clips with music.
  - For battle clips with music, `Replay battle music when finished` can be toggled for the session and applied back to the campaign.
- Use `Apply Clip Changes to Campaign` to write clip-level overrides into authored timeline.
- Use `Reset Session Overrides` to clear runtime clip and skip-range overrides.

## 10) Battle Map Controls
- Left-click token: select token.
- Left-click drag token:
  - Before combat: reposition token using the movement preview/confirmation flow.
  - During combat: only the active-turn token can be drag-moved.
  - Uses the same yellow movement range indicator and path preview as `Move Token...`.
  - Large tokens use footprint-aware movement/placement checks (for example, a `2x2` token cannot move through spaces its full footprint would overlap).
- Left-drag background or middle-drag: pan map.
- Mouse wheel: zoom centered at cursor.
  - When the cursor is over the battle log panel, the wheel scrolls the log instead of zooming the map.
- Player-view battle camera can be toggled from `View -> Player Battle: Follow DM Camera`.
  - On: the player view follows DM pan/zoom, but clamps to the map and falls back to the normal full-map render if the DM zooms out beyond what the player view can show cleanly.
  - Off: the player view stays on the normal full-map battle render.
- Player-view battle zoom can be toggled from `View -> Player Battle: Follow DM Zoom`.
  - On: when full DM camera follow is off, the player view uses the DM zoom level while staying centered on the map.
- Player-view battle rendering mode can be toggled from `View -> Player Battle: Preserve Aspect Ratio`.
  - On (default): preserves map aspect ratio (no stretching, may letterbox).
  - Off: fills the player screen.
- Battle log panel (bottom-left overlay):
  - Scrollable with mouse wheel and scrollbar to review previous combat entries.
  - Resizable during battle from the panel's resize handle (size resets between sessions/encounters).
- Right-click token opens action and management menu:
  - `Actions` submenu:
    - `Single Target Attack...`
    - `AOE Attack...`
    - `Ready Action/Reaction`
    - `Log Custom Action...`
  - `Move Token...`
  - `Set Status` submenu (including concentration controls)
  - `Death Saves` submenu (when token is unconscious)
  - `Manage Conditions...` submenu with toggleable condition entries
  - `Notes...` for encounter-only DM notes on that token
  - `Remove Token`
- Non-square tokens also get `Rotate Token` in the context menu to swap footprint orientation when the rotated footprint still fits.
- `Single Target Attack...` and `AOE Attack...` open the `Resolve Action` workflow to log outcome, damage/healing, conditions, and notes.
- `Log Custom Action...` opens the `Log Custom Action` dialog for log-only entries without applying combat effects.
- AOE workflow:
  - Choose `AOE Attack...`, then click a grid square for the AOE origin.
  - The `Select AOE Hits` dialog opens with candidate tokens, footprint-aware distances, and checkboxes.
  - Check targets that were hit, then use `Move Up` / `Move Down` to control resolve order.
  - The tool runs sequential `Resolve Action` dialogs for the selected targets.
- `Ready Action/Reaction` is a manual combat toggle/marker on the token's turn (optional for table tracking).
- Off-turn `Single Target Attack...` can be used manually as a reaction when the token still has a reaction available this round (the tool does not detect triggers; DM/player adjudicates when the trigger happens).
- Opportunity attack prompts may appear during movement when a hostile token can react; taking one consumes that token's reaction for the round.
- Active-turn indicator arrow remains visible above the current token for the full turn (including in player view).
- Status / concentration controls:
  - `Concentration...` starts concentration and asks for a duration (rounds).
  - `End Concentration` clears concentration manually.
  - Token context info shows concentration rounds remaining when active.
- Right-click background menu:
  - Start Combat, End Combat, Next Turn, End Encounter, Fit View
- Keyboard:
  - `N` advances turn (when valid)
  - `Esc` cancels selection modes first, otherwise ends encounter

## 11) Combat Rules Implemented in Tooling
- Start Combat requires initiative set for alive tokens unless `Full Manual` is enabled.
- Initiative order sorting: initiative roll first, then DEX bonus tie-break.
- In active combat, token actions are constrained by turn and status (with manual off-turn reaction support for `Single Target Attack...` when a reaction is available). `Full Manual` can temporarily disable these enforcement checks.
- Opportunity attacks:
  - The tool can prompt for opportunity attacks during qualifying movement.
  - Opportunity-attack adjacency checks account for large token footprints.
  - Same-team tokens do not trigger opportunity attacks against each other when teams are assigned.
  - A token's reaction limit is tracked, which also limits readied reactions/opportunity attacks each round.
- `Ready Action/Reaction` can be used as an on-turn manual marker, and the tool tracks each token's reaction limit per round.
- Off-turn `Single Target Attack...` can be used as a manual reaction if the token is eligible and has not spent its reaction this round.
- Concentration:
  - Can be started with a tracked duration.
  - Can end from death/unconscious outcomes or manual end.
  - Taking damage can trigger a concentration save prompt (DM adjudicates pass/fail in the prompt).
  - Timed concentration can expire during turn progression.
- Action resolution dialogs can apply damage/healing, conditions, and optional condition durations.
- Death-save actions are available for unconscious status and update persistent logic.

## 12) Token Profiles and Persistence
- Profiles store base combat fields and persistent values (including current HP, death saves, token footprint size, and token visual-fit mode).
- You can edit profiles from:
  - `Edit -> Manage Token Profiles`
  - Encounter Setup token-list context menu
  - DM Live Control Panel -> Encounter Token Controls -> `Edit Profile...` (opens Token Profile Management first)
- Profile `Size` is entered with two fields (`W x H`) plus a `grid squares` label for clarity.
- `Visual Fit` controls whether token art stretches to fill its footprint or stays contained inside it.
- Initiative values and team assignments are encounter runtime data managed from DM tools / Initiative Manager (not token profile base stats).
- Deleting a profile removes stored base/persistent values.
- If a deleted profile token is used again later, it falls back to defaults.

## 13) Saving, Loading, and Portability
- Default save uses packaged `.dcp` format with manifest plus bundled assets.
- Legacy plain JSON `.dcp` files are still load-compatible.
- In-progress encounter runtime state is saved and can be restored (for example: initiative order/current round, team assignments, active conditions and tracked durations, concentration state, reaction/readied-reaction state during combat, and `Full Manual` mode state).
- Runtime encounter state also preserves placed-token display data such as footprint size, visual fit, and token rotation.
- If referenced source assets are missing at save time, unresolved paths may remain for troubleshooting.

## 14) Common Troubleshooting
- No audio playback: app can continue in no-audio mode if mixer init fails.
- Token not in Tokens tab: verify the filename includes a token marker such as `(token)`, or import with the Token filter and a supported token extension.
- Large token looks blurry when resized: higher-resolution source token art gives better results; the app now scales from the source image, but low-res source art will still look soft when enlarged.
- Combat will not start: open DM Panel -> `Manage Initiative...` and set initiative for each alive token, or enable `Full Manual` if you want to run the encounter without rule enforcement.
- AOE attack won't start: after choosing `AOE Attack...`, click a valid grid square on the map for the origin.
- AOE resolves no targets: in `Select AOE Hits`, check at least one target before clicking OK.
- Off-turn reaction attack not available: the token may be incapacitated/not alive, combat may be inactive, or that token's reaction may already be spent this round.
- No opportunity attack prompt appeared: tokens on the same assigned team are treated as non-hostile, or the reacting token may already have spent its reaction.
- Concentration ended unexpectedly: concentration can end from damage (failed save), unconscious/dead states, manual end, or duration expiration.
- Missing image/audio after load: verify files exist, then re-import and resave package.
- DM panel clip selection seems to reset: ensure you are selecting in the DM panel list/mini timeline, then adjust controls there.
- Skip range did not apply: drawing only fills start/end fields; click `Add Range` to commit.

## 15) Feedback Notes and Bug Reports
- Open `Help -> Feedback Notes...` to record issues, bugs, and errors for the maintainer.
- Fill in type, severity, summary, workflow area, repro steps, expected behavior, and actual behavior.
- Paste traceback or log snippets in the Error/Logs field when available.
- Use `Copy Report` to paste into chat/email, or `Save Report...` to export a `.txt` file.
- Include one report per issue when possible to keep triage clear.

## 15) AI Art Consistency Guide (Battle Maps + Tokens)
- Keep one shared art direction across your campaign assets:
  - hand-painted fantasy tabletop look
  - readable silhouettes and terrain shapes
  - no text, UI elements, logos, or watermarks

- Battle maps (environment assets):
  - Use a top-down / bird's-eye camera angle (near-orthographic).
  - Keep tactical readability first: paths, walls, cover, and hazards should be easy to distinguish.
  - Leave enough open playable space for token movement and combat positioning.
  - Don't try to have the grid built-in to the map you generate, the program can apply one for you when you set up an encounter.
  - Prompt starter:
    - `top-down fantasy battle map, hand-painted tabletop style, readable terrain, clear walkable paths and cover, no characters, no text, no UI, no watermark`

- Tokens (character/creature assets):
  - Use a miniature/figure look, with full body visible and clean silhouette.
  - Keep a consistent facing direction across your token set (for example, facing upper-right).
  - Choose one token base style and keep it consistent:
    - with a round base/platform (tabletop mini look), or
    - platformless figure/cutout style.
    - Use no/ or transparent background.
  - Prompt starter:
   - STYLE/ANGLE: D&D token art, three-quarter top-down (30–40°), painterly, crisp lines, high detail, transparent background. SUBJECT: [SPECIES] [CLASS] wearing [ARMOR], holding [WEAPON], [COLOR ACCENTS], [POSE]. BASE (optional): [ON ROUND BASE: grass/stone/dirt + stone rim] OR [NO BASE: character only + subtle shadow]. NEGATIVES: no scene/background, no text, no extra characters, no border/watermark, no cropping/cut limbs.
   - Consistency workflow tip:
   - Save a prompt template for maps and one for tokens, then only swap subject/location details per asset.
"""
