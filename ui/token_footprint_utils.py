from __future__ import annotations

from typing import Any, Mapping

DEFAULT_TOKEN_FOOTPRINT_WIDTH = 1
DEFAULT_TOKEN_FOOTPRINT_HEIGHT = 1
MAX_TOKEN_FOOTPRINT_DIMENSION = 10
DEFAULT_TOKEN_VISUAL_FIT_MODE = "stretch"
TOKEN_VISUAL_FIT_MODES = ("stretch", "contain")


def normalize_footprint_dimension(raw: Any, default: int = DEFAULT_TOKEN_FOOTPRINT_WIDTH) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(1, min(MAX_TOKEN_FOOTPRINT_DIMENSION, value))


def normalize_footprint_dimensions(
    raw_width: Any = None,
    raw_height: Any = None,
    legacy_size: Any = None,
) -> tuple[int, int]:
    legacy_default = normalize_footprint_dimension(legacy_size, DEFAULT_TOKEN_FOOTPRINT_WIDTH)
    width = normalize_footprint_dimension(
        raw_width,
        legacy_default if raw_width is None else DEFAULT_TOKEN_FOOTPRINT_WIDTH,
    )
    height = normalize_footprint_dimension(
        raw_height,
        legacy_default if raw_height is None else DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
    )
    return width, height


def get_footprint_dimensions(data: Mapping[str, Any] | None) -> tuple[int, int]:
    if not isinstance(data, Mapping):
        return DEFAULT_TOKEN_FOOTPRINT_WIDTH, DEFAULT_TOKEN_FOOTPRINT_HEIGHT
    return normalize_footprint_dimensions(
        data.get("footprint_w"),
        data.get("footprint_h"),
        data.get("size_squares"),
    )


def normalize_visual_fit_mode(raw: Any) -> str:
    mode = str(raw or DEFAULT_TOKEN_VISUAL_FIT_MODE).strip().lower()
    if mode not in TOKEN_VISUAL_FIT_MODES:
        return DEFAULT_TOKEN_VISUAL_FIT_MODE
    return mode

