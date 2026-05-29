import os
import re
from typing import Any


_TOKEN_MARKER_PATTERN = re.compile(r"\(\s*token\s*\)", re.IGNORECASE)
_WHITESPACE_PATTERN = re.compile(r"\s+")


def derive_profile_name_from_path(token_path: str) -> str:
    stem = os.path.splitext(os.path.basename(token_path))[0]
    stem = _TOKEN_MARKER_PATTERN.sub("", stem)
    stem = stem.replace("_", " ").replace("-", " ")
    stem = _WHITESPACE_PATTERN.sub(" ", stem).strip()
    return stem or "Token"


def normalize_profile_name(raw_name: Any, token_path: str) -> str:
    if raw_name is None:
        candidate = ""
    elif isinstance(raw_name, str):
        candidate = raw_name
    else:
        candidate = str(raw_name)
    candidate = _WHITESPACE_PATTERN.sub(" ", candidate).strip()
    return candidate or derive_profile_name_from_path(token_path)


def ensure_profile_name(profile: Any, token_path: str) -> str:
    name = normalize_profile_name(profile.get("name") if isinstance(profile, dict) else None, token_path)
    if isinstance(profile, dict):
        profile["name"] = name
    return name
