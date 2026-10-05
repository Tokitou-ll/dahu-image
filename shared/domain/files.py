"""收集用户选中的图片路径。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".jpe",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    ".heic",
    ".heif",
)

_NATURAL_SPLIT = re.compile(r"(\d+)")


@dataclass(frozen=True)
class CollectedInputs:
    images: list[str]
    skipped: list[str]
    missing: list[str]


def image_dialog_filter() -> str:
    patterns = " ".join(f"*{extension}" for extension in SUPPORTED_EXTENSIONS)
    return f"图片 ({patterns})"


def natural_key(name: str) -> list[int | str]:
    parts: list[int | str] = []
    for part in _NATURAL_SPLIT.split(name):
        parts.append(int(part) if part.isdigit() else part.casefold())
    return parts


def collect_inputs(raw_paths: list[str]) -> CollectedInputs:
    """展开文件和文件夹。文件夹只取当前这一层，并按文件名自然排序。"""
    images: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()

    def add_file(path: Path) -> None:
        if path.name.startswith("."):
            return
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped.append(str(path))
            return
        try:
            if path.stat().st_size <= 0:
                skipped.append(str(path))
                return
            resolved = str(path.resolve())
        except OSError:
            missing.append(str(path))
            return
        if resolved in seen:
            return
        seen.add(resolved)
        images.append(resolved)

    for raw in raw_paths:
        path = Path(raw).expanduser()
        if not path.exists():
            missing.append(str(path))
            continue
        if path.is_dir():
            children = [child for child in path.iterdir() if child.is_file()]
            children.sort(key=lambda child: natural_key(child.name))
            for child in children:
                add_file(child)
            continue
        if path.is_file():
            add_file(path)
    return CollectedInputs(images, skipped, missing)
