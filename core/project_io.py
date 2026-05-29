from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Any

PACKAGE_MANIFEST_NAME = "manifest.json"
PACKAGE_FORMAT = "dcp_package_v1"
ASSET_URI_PREFIX = "asset://"
LATEST_PROJECT_VERSION = "1.5"


@dataclass
class LoadedProject:
    project_data: dict[str, Any]
    extracted_dir: str | None = None


def _normalize_asset_path(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def _asset_uri(asset_id: str) -> str:
    return f"{ASSET_URI_PREFIX}{asset_id}"


def _asset_id_from_uri(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    if not value.startswith(ASSET_URI_PREFIX):
        return None
    return value[len(ASSET_URI_PREFIX):]


def _cleanup_extracted_dir(extracted_dir: str) -> None:
    if os.path.isdir(extracted_dir):
        try:
            shutil.rmtree(extracted_dir)
        except Exception:
            # Best-effort cleanup path for temporary extracted package contents.
            pass


def _resolve_package_asset_path(extracted_dir: str, rel_filename: Any) -> str:
    if not isinstance(rel_filename, str) or not rel_filename:
        raise ValueError("Invalid project package: asset_index entry is missing a valid filename.")

    extracted_root = os.path.normpath(extracted_dir)
    candidate_path = os.path.normpath(os.path.join(extracted_root, rel_filename))
    if os.path.commonpath([extracted_root, candidate_path]) != extracted_root:
        raise ValueError(f"Invalid project package: asset path escapes package root ({rel_filename}).")
    if not os.path.exists(candidate_path):
        raise ValueError(f"Invalid project package: referenced asset is missing ({rel_filename}).")
    return candidate_path


def _preferred_asset_display_name(asset_info: dict[str, Any], rel_filename: str, source_path: str) -> str:
    original_name = asset_info.get("original_name")
    if isinstance(original_name, str):
        cleaned_original_name = os.path.basename(original_name.strip())
        if cleaned_original_name:
            return cleaned_original_name

    original_path = asset_info.get("original_path")
    if isinstance(original_path, str):
        basename_from_original_path = os.path.basename(original_path.strip())
        if basename_from_original_path:
            return basename_from_original_path

    rel_basename = os.path.basename(rel_filename.strip())
    if rel_basename:
        return rel_basename

    source_basename = os.path.basename(source_path)
    if source_basename:
        return source_basename
    return "asset"


def _materialize_display_asset_path(
    display_dir: str,
    source_path: str,
    preferred_name: str,
    used_display_names: set[str],
) -> str:
    clean_preferred_name = os.path.basename(preferred_name.strip())
    if not clean_preferred_name:
        clean_preferred_name = os.path.basename(source_path) or "asset"

    stem, extension = os.path.splitext(clean_preferred_name)
    if not stem:
        stem = "asset"
    if not extension:
        _, source_extension = os.path.splitext(source_path)
        extension = source_extension

    candidate_name = f"{stem}{extension}"
    suffix = 2
    while candidate_name.lower() in used_display_names:
        candidate_name = f"{stem}_{suffix}{extension}"
        suffix += 1
    used_display_names.add(candidate_name.lower())

    target_path = os.path.join(display_dir, candidate_name)
    source_abs = os.path.abspath(source_path)
    target_abs = os.path.abspath(target_path)
    if source_abs == target_abs:
        return source_path

    try:
        shutil.copy2(source_path, target_path)
    except OSError:
        return source_path
    return target_path


def _iter_referenced_asset_paths(project_data: dict[str, Any]) -> set[str]:
    paths: set[str] = set()

    assets = project_data.get("assets", {})
    if isinstance(assets, dict):
        for category in ("images", "audio", "tokens"):
            category_paths = assets.get(category, [])
            if isinstance(category_paths, list):
                for path in category_paths:
                    if isinstance(path, str) and path:
                        paths.add(_normalize_asset_path(path))

    timeline = project_data.get("timeline", [])
    if isinstance(timeline, list):
        for clip in timeline:
            if not isinstance(clip, dict):
                continue
            track = clip.get("track")
            if track in ("Image", "Audio"):
                clip_path = clip.get("path")
                if isinstance(clip_path, str) and clip_path:
                    paths.add(_normalize_asset_path(clip_path))
            elif track == "Battle":
                map_path = clip.get("map_path")
                if isinstance(map_path, str) and map_path:
                    paths.add(_normalize_asset_path(map_path))

                battle_music = clip.get("battle_music_path")
                if isinstance(battle_music, str) and battle_music:
                    paths.add(_normalize_asset_path(battle_music))

                tokens = clip.get("tokens", [])
                if isinstance(tokens, list):
                    for token in tokens:
                        if isinstance(token, dict):
                            token_path = token.get("path")
                            if isinstance(token_path, str) and token_path:
                                paths.add(_normalize_asset_path(token_path))

    token_profiles = project_data.get("token_profiles", {})
    if isinstance(token_profiles, dict):
        for token_path in token_profiles.keys():
            if isinstance(token_path, str) and token_path:
                paths.add(_normalize_asset_path(token_path))

    encounter_runtime = project_data.get("encounter_runtime", {})
    if isinstance(encounter_runtime, dict):
        for runtime in encounter_runtime.values():
            if not isinstance(runtime, dict):
                continue
            runtime_map = runtime.get("map_path")
            if isinstance(runtime_map, str) and runtime_map:
                paths.add(_normalize_asset_path(runtime_map))

            runtime_music = runtime.get("battle_music_path")
            if isinstance(runtime_music, str) and runtime_music:
                paths.add(_normalize_asset_path(runtime_music))

            runtime_tokens = runtime.get("tokens", [])
            if isinstance(runtime_tokens, list):
                for token in runtime_tokens:
                    if isinstance(token, dict):
                        token_path = token.get("path")
                        if isinstance(token_path, str) and token_path:
                            paths.add(_normalize_asset_path(token_path))
                        skin_path = token.get("skin_path")
                        if isinstance(skin_path, str) and skin_path:
                            paths.add(_normalize_asset_path(skin_path))

    return paths


def _replace_paths_with_asset_uris(project_data: dict[str, Any], path_to_asset_id: dict[str, str]) -> dict[str, Any]:
    data = copy.deepcopy(project_data)

    def rewrite_path(value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value
        normalized = _normalize_asset_path(value)
        asset_id = path_to_asset_id.get(normalized)
        if asset_id is None:
            return value
        return _asset_uri(asset_id)

    assets = data.get("assets", {})
    if isinstance(assets, dict):
        for category in ("images", "audio", "tokens"):
            category_paths = assets.get(category)
            if isinstance(category_paths, list):
                assets[category] = [rewrite_path(path) for path in category_paths]

    timeline = data.get("timeline", [])
    if isinstance(timeline, list):
        for clip in timeline:
            if not isinstance(clip, dict):
                continue
            clip["path"] = rewrite_path(clip.get("path"))
            clip["map_path"] = rewrite_path(clip.get("map_path"))
            clip["battle_music_path"] = rewrite_path(clip.get("battle_music_path"))

            tokens = clip.get("tokens")
            if isinstance(tokens, list):
                for token in tokens:
                    if isinstance(token, dict):
                        token["path"] = rewrite_path(token.get("path"))
                        token["skin_path"] = rewrite_path(token.get("skin_path"))

    profiles = data.get("token_profiles", {})
    if isinstance(profiles, dict):
        rewritten_profiles: dict[str, Any] = {}
        for token_path, profile in profiles.items():
            if isinstance(token_path, str):
                rewritten_profiles[rewrite_path(token_path)] = profile
        data["token_profiles"] = rewritten_profiles

    encounter_runtime = data.get("encounter_runtime", {})
    if isinstance(encounter_runtime, dict):
        for runtime in encounter_runtime.values():
            if not isinstance(runtime, dict):
                continue
            runtime["map_path"] = rewrite_path(runtime.get("map_path"))
            runtime["battle_music_path"] = rewrite_path(runtime.get("battle_music_path"))
            tokens = runtime.get("tokens")
            if isinstance(tokens, list):
                for token in tokens:
                    if isinstance(token, dict):
                        token["path"] = rewrite_path(token.get("path"))
                        token["skin_path"] = rewrite_path(token.get("skin_path"))

    data["version"] = LATEST_PROJECT_VERSION
    return data


def _replace_asset_uris_with_paths(project_data: dict[str, Any], asset_id_to_path: dict[str, str]) -> dict[str, Any]:
    data = copy.deepcopy(project_data)

    def resolve_uri(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        asset_id = _asset_id_from_uri(value)
        if asset_id is None:
            return value
        return asset_id_to_path.get(asset_id, value)

    assets = data.get("assets", {})
    if isinstance(assets, dict):
        for category in ("images", "audio", "tokens"):
            category_paths = assets.get(category)
            if isinstance(category_paths, list):
                assets[category] = [resolve_uri(path) for path in category_paths]

    timeline = data.get("timeline", [])
    if isinstance(timeline, list):
        for clip in timeline:
            if not isinstance(clip, dict):
                continue
            clip["path"] = resolve_uri(clip.get("path"))
            clip["map_path"] = resolve_uri(clip.get("map_path"))
            clip["battle_music_path"] = resolve_uri(clip.get("battle_music_path"))

            tokens = clip.get("tokens")
            if isinstance(tokens, list):
                for token in tokens:
                    if isinstance(token, dict):
                        token["path"] = resolve_uri(token.get("path"))
                        token["skin_path"] = resolve_uri(token.get("skin_path"))

    profiles = data.get("token_profiles", {})
    if isinstance(profiles, dict):
        rewritten_profiles: dict[str, Any] = {}
        for token_path, profile in profiles.items():
            rewritten_profiles[resolve_uri(token_path)] = profile
        data["token_profiles"] = rewritten_profiles

    encounter_runtime = data.get("encounter_runtime", {})
    if isinstance(encounter_runtime, dict):
        for runtime in encounter_runtime.values():
            if not isinstance(runtime, dict):
                continue
            runtime["map_path"] = resolve_uri(runtime.get("map_path"))
            runtime["battle_music_path"] = resolve_uri(runtime.get("battle_music_path"))
            tokens = runtime.get("tokens")
            if isinstance(tokens, list):
                for token in tokens:
                    if isinstance(token, dict):
                        token["path"] = resolve_uri(token.get("path"))
                        token["skin_path"] = resolve_uri(token.get("skin_path"))

    return data


def save_project_package(file_path: str, project_data: dict[str, Any]) -> None:
    referenced_paths = _iter_referenced_asset_paths(project_data)

    path_to_asset_id: dict[str, str] = {}
    asset_index: dict[str, dict[str, str]] = {}

    ordered_paths = sorted(referenced_paths)
    asset_counter = 0
    for source_path in ordered_paths:
        if not os.path.exists(source_path):
            # Keep unresolved paths in manifest as-is so users can still diagnose issues.
            continue

        asset_id = f"a{asset_counter:04d}"
        asset_counter += 1

        _, extension = os.path.splitext(source_path)
        extension = extension.lower()
        relative_name = f"assets/{asset_id}{extension}"

        path_to_asset_id[source_path] = asset_id
        asset_index[asset_id] = {
            "filename": relative_name,
            "original_name": os.path.basename(source_path),
            "original_path": source_path,
        }

    manifest_data = _replace_paths_with_asset_uris(project_data, path_to_asset_id)
    manifest_data["package_format"] = PACKAGE_FORMAT
    manifest_data["asset_index"] = asset_index

    with zipfile.ZipFile(file_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(PACKAGE_MANIFEST_NAME, json.dumps(manifest_data, indent=2))
        for source_path, asset_id in path_to_asset_id.items():
            target_info = asset_index[asset_id]
            archive.write(source_path, target_info["filename"])


def load_project_file(file_path: str) -> LoadedProject:
    if not zipfile.is_zipfile(file_path):
        with open(file_path, "r", encoding="utf-8") as handle:
            legacy_data = json.load(handle)
        return LoadedProject(project_data=legacy_data, extracted_dir=None)

    extracted_dir = tempfile.mkdtemp(prefix="dcp_project_")
    load_succeeded = False
    try:
        with zipfile.ZipFile(file_path, "r") as archive:
            archive.extractall(extracted_dir)

        manifest_path = os.path.join(extracted_dir, PACKAGE_MANIFEST_NAME)
        if not os.path.isfile(manifest_path):
            raise ValueError("Invalid project package: missing manifest.json.")

        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest_data = json.load(handle)
        if not isinstance(manifest_data, dict):
            raise ValueError("Invalid project package: manifest.json must contain a JSON object.")

        package_format = manifest_data.get("package_format")
        if package_format != PACKAGE_FORMAT:
            raise ValueError(
                f"Invalid project package: unsupported package format '{package_format}'."
            )

        asset_index = manifest_data.get("asset_index", {})
        if not isinstance(asset_index, dict):
            raise ValueError("Invalid project package: asset_index must be a JSON object.")

        asset_id_to_path: dict[str, str] = {}
        display_asset_dir = os.path.join(extracted_dir, "assets_display")
        os.makedirs(display_asset_dir, exist_ok=True)
        used_display_names: set[str] = set()
        for asset_id, info in asset_index.items():
            if not isinstance(asset_id, str) or not asset_id:
                raise ValueError("Invalid project package: asset_index contains an invalid asset ID.")
            if not isinstance(info, dict):
                raise ValueError(
                    f"Invalid project package: asset_index entry '{asset_id}' must be a JSON object."
                )
            rel_filename = info.get("filename")
            source_path = _resolve_package_asset_path(extracted_dir, rel_filename)
            preferred_name = _preferred_asset_display_name(info, rel_filename, source_path)
            asset_id_to_path[asset_id] = _materialize_display_asset_path(
                display_asset_dir,
                source_path,
                preferred_name,
                used_display_names,
            )

        project_data = _replace_asset_uris_with_paths(manifest_data, asset_id_to_path)
        project_data.pop("asset_index", None)
        project_data.pop("package_format", None)

        load_succeeded = True
        return LoadedProject(project_data=project_data, extracted_dir=extracted_dir)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid project package JSON content: {exc}") from exc
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"Could not open project package '{os.path.basename(file_path)}': {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"Failed to load project package '{os.path.basename(file_path)}': {exc}") from exc
    finally:
        if not load_succeeded:
            _cleanup_extracted_dir(extracted_dir)
